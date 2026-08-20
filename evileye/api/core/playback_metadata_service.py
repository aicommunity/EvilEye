"""Build StreamMetadata-compatible overlay payloads for archive playback."""

from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from evileye.api.core.playback_service import _config_path_for_run, _configured_data_dir_from_params, data_dir
from evileye.visualization_modules.journal_metadata_extractor import EventMetadataExtractor
from evileye.visualization_modules.overlay_config import extract_zones_by_source
from evileye.visualization_modules.playback_coord import (
    PlaybackCoordContext,
    resolve_playback_coord_context,
    source_aliases,
)
from evileye.visualization_modules.preview_render import PreviewRenderContext, serialize_preview_metadata

_OBJECT_FILES = ("objects_found.json", "objects_lost.json")
DEFAULT_MATCH_SEC = 0.5
MAX_LERP_SEC = 600.0
INDEX_TTL_SEC = 45.0
DETECTION_INDEX_CACHE: dict[str, tuple[float, float, list[dict[str, Any]]]] = {}
DAY_CAMERA_INDEX_CACHE: dict[str, tuple[float, float, dict[str, list[dict[str, Any]]]]] = {}
JSON_OBJECTS_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_EVENT_FILES = {
    "camera_events.json": "camera_events",
    "system_events.json": "system_events",
    "zone_events_entered.json": "zone_events_entered",
    "zone_events_left.json": "zone_events_left",
    "attribute_events_found.json": "attribute_events_found",
    "attribute_events_finished.json": "attribute_events_finished",
}
_TIMESTAMP_FORMATS = (
    "%Y-%m-%d %H:%M:%S.%f",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
)


def parse_event_timestamp(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value))
        except Exception:
            return None
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1]
        for fmt in _TIMESTAMP_FORMATS:
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
    except Exception:
        return None
    return None


def _load_params_for_run(run_id: int | None) -> dict[str, Any]:
    if run_id is not None:
        try:
            from evileye.api.core.server_state import get_run_summary

            summary = get_run_summary(int(run_id))
            if isinstance(summary, dict):
                snapshot = summary.get("runtime_snapshot")
                if isinstance(snapshot, dict):
                    payload = snapshot.get("config")
                    if isinstance(payload, dict):
                        return payload
        except Exception:
            pass
        config_path = _config_path_for_run(run_id)
        if config_path:
            try:
                payload = json.loads(Path(config_path).read_text(encoding="utf-8"))
                return payload if isinstance(payload, dict) else {}
            except Exception:
                pass
        return {}
    from evileye.api.core.journal_service import _runtime_params

    return _runtime_params()


def _resolve_source_id(
    params: dict[str, Any],
    camera: str,
    source_id: int | None,
) -> int | None:
    if source_id is not None:
        return source_id
    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        names = source.get("source_names") or []
        ids = source.get("source_ids") or []
        for idx, name in enumerate(names):
            if str(name) == camera and idx < len(ids):
                try:
                    return int(ids[idx])
                except Exception:
                    return None
        split = bool(source.get("split"))
        num_split = int(source.get("num_split") or len(names) or 0)
        if split and num_split and names:
            parent_folder = "-".join(str(n) for n in names[:num_split])
            if camera == parent_folder:
                try:
                    return int(ids[0]) if ids else None
                except Exception:
                    return None
    try:
        from evileye.api.core.server_state import load_config_summary

        summary = load_config_summary(_config_path_for_run(None))
        for item in summary.source_items:
            if str(item.get("source_name")) == camera:
                sid = item.get("source_id")
                return int(sid) if sid is not None else None
            parent = item.get("parent_source_name")
            if parent and str(parent) == camera:
                sid = item.get("source_id")
                return int(sid) if sid is not None else None
    except Exception:
        pass
    return None


def _playback_storage_mode(params: dict[str, Any]) -> str:
    from evileye.api.core.server_state import storage_mode_from_params

    return storage_mode_from_params(params)


def _playback_data_dir(params: dict[str, Any]) -> Path:
    configured = _configured_data_dir_from_params(params)
    if configured:
        return Path(configured).resolve()
    return data_dir()


def _record_matches_camera(
    raw: dict[str, Any],
    *,
    aliases: set[str],
    source_id: int | None,
) -> bool:
    raw_sid = raw.get("source_id")
    if source_id is not None and raw_sid is not None:
        try:
            return int(raw_sid) == int(source_id)
        except Exception:
            pass
    obj_source = raw.get("source_name") or raw.get("source")
    if obj_source and str(obj_source) in aliases:
        return True
    return not obj_source


def _wall_event_time(raw: dict[str, Any], kind: str | None = None) -> datetime | None:
    if kind == "lost":
        keys = ("lost_timestamp", "timestamp", "ts", "time_stamp")
    elif kind == "found":
        keys = ("timestamp", "detected_timestamp", "ts", "time_stamp")
    else:
        keys = ("timestamp", "detected_timestamp", "ts", "time_stamp", "lost_timestamp")
    for key in keys:
        ts = parse_event_timestamp(raw.get(key))
        if ts:
            return ts
    return None


def _unix_from_media_pts(raw: dict[str, Any], camera: str, date_folder: str) -> float | None:
    media = raw.get("media_pts_sec")
    if media is None:
        return None
    try:
        media_f = float(media)
    except (TypeError, ValueError):
        return None
    wall = _wall_event_time(raw)
    around = wall.timestamp() if wall else None
    from evileye.api.core.playback_service import session_anchor_ts_for_camera

    start = session_anchor_ts_for_camera(camera, date_folder, around_ts=around)
    if start is None:
        return None
    return float(start) + media_f


def _record_event_time(
    raw: dict[str, Any],
    *,
    camera: str | None = None,
    date_folder: str | None = None,
    kind: str | None = None,
) -> datetime | None:
    if camera and date_folder:
        unix = _unix_from_media_pts(raw, camera, date_folder)
        if unix is not None:
            return datetime.fromtimestamp(unix)
    return _wall_event_time(raw, kind)


def _read_json_objects(filepath: Path) -> list[dict[str, Any]]:
    if not filepath.is_file():
        return []
    try:
        mtime = filepath.stat().st_mtime
    except OSError:
        return []
    key = str(filepath)
    cached = JSON_OBJECTS_CACHE.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return []
    objects_list = data if isinstance(data, list) else data.get("objects", [])
    parsed = [obj for obj in objects_list if isinstance(obj, dict)]
    JSON_OBJECTS_CACHE[key] = (mtime, parsed)
    return parsed


def _detection_event_ts(
    raw: dict[str, Any],
    kind: str,
    *,
    camera: str | None = None,
    date_folder: str | None = None,
) -> datetime | None:
    return _record_event_time(raw, camera=camera, date_folder=date_folder, kind=kind)


def _is_today_folder(date_folder: str) -> bool:
    return date_folder == datetime.now().strftime("%Y-%m-%d")


def _index_cache_valid(cached_mtime: float, cached_at: float, json_mtime: float, date_folder: str) -> bool:
    if cached_mtime == json_mtime:
        return True
    return _is_today_folder(date_folder) and (time.time() - cached_at) < INDEX_TTL_SEC


def _tick_only_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "ts": item["ts"],
        "kind": item.get("kind"),
        "object_id": item.get("object_id"),
    }


def _filter_index_window(
    items: list[dict[str, Any]],
    from_ts: float | None,
    to_ts: float | None,
    *,
    ticks_only: bool = False,
) -> list[dict[str, Any]]:
    filtered = items
    if from_ts is not None:
        filtered = [row for row in filtered if row["ts"] >= float(from_ts)]
    if to_ts is not None:
        filtered = [row for row in filtered if row["ts"] <= float(to_ts)]
    if ticks_only:
        return [_tick_only_item(row) for row in filtered]
    return filtered


def _index_cache_key(base: Path, date_folder: str, camera: str, source_id: int | None) -> str:
    return f"{base}:{date_folder}:{camera}:{source_id}"


def _day_cache_key(base: Path, date_folder: str, run_id: int | None) -> str:
    return f"{base}:{date_folder}:{run_id if run_id is not None else 'none'}"


def _file_mtime_sum(*paths: Path) -> float:
    total = 0.0
    for path in paths:
        try:
            if path.is_file():
                total += path.stat().st_mtime
        except OSError:
            continue
    return total


def _sidecar_mtime_sum(base: Path, date_folder: str) -> float:
    streams = base / "Streams" / date_folder
    if not streams.is_dir():
        return 0.0
    try:
        paths = list(streams.glob("**/*.session.json"))
    except OSError:
        return 0.0
    return _file_mtime_sum(*paths)


def _detection_index_item(
    raw: dict[str, Any],
    kind: str,
    *,
    camera: str | None = None,
    date_folder: str | None = None,
) -> dict[str, Any] | None:
    event_ts = _detection_event_ts(raw, kind, camera=camera, date_folder=date_folder)
    if not event_ts:
        return None
    return {
        "ts": event_ts.timestamp(),
        "kind": kind,
        "object_id": raw.get("object_id"),
        "source_name": raw.get("source_name") or raw.get("source"),
        "source_id": raw.get("source_id"),
        "bounding_box": raw.get("bounding_box") or raw.get("box"),
        "frame_id": raw.get("frame_id"),
        "class_name": raw.get("class_name"),
        "confidence": raw.get("confidence"),
        "class_id": raw.get("class_id"),
        "track_id": raw.get("track_id"),
        "global_id": raw.get("global_id"),
    }


def _build_camera_index_items(
    *,
    found_path: Path,
    lost_path: Path,
    camera: str,
    date_folder: str,
    aliases: set[str],
    source_id: int | None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for obj in _read_json_objects(found_path):
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            continue
        item = _detection_index_item(obj, "found", camera=camera, date_folder=date_folder)
        if item:
            items.append(item)
    for obj in _read_json_objects(lost_path):
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            continue
        item = _detection_index_item(obj, "lost", camera=camera, date_folder=date_folder)
        if item:
            items.append(item)
    items.sort(key=lambda row: row["ts"])
    return items


def _load_camera_index_items(
    *,
    base: Path,
    date_folder: str,
    camera: str,
    params: dict[str, Any],
    source_id: int | None,
) -> list[dict[str, Any]]:
    sid = source_id if source_id is not None else _resolve_source_id(params, camera, source_id)
    aliases = source_aliases(params, camera, sid)
    found_path = base / "Detections" / date_folder / "Metadata" / "objects_found.json"
    lost_path = base / "Detections" / date_folder / "Metadata" / "objects_lost.json"
    json_mtime = _file_mtime_sum(found_path, lost_path)
    cache_key = _index_cache_key(base, date_folder, camera, sid)
    cached = DETECTION_INDEX_CACHE.get(cache_key)
    if cached and _index_cache_valid(cached[0], cached[1], json_mtime, date_folder):
        return cached[2]
    items = _build_camera_index_items(
        found_path=found_path,
        lost_path=lost_path,
        camera=camera,
        date_folder=date_folder,
        aliases=aliases,
        source_id=sid,
    )
    DETECTION_INDEX_CACHE[cache_key] = (json_mtime, time.time(), items)
    return items


def _load_day_index_by_camera(
    *,
    base: Path,
    date_folder: str,
    run_id: int | None,
    params: dict[str, Any],
    cameras: list[str],
) -> dict[str, list[dict[str, Any]]]:
    found_path = base / "Detections" / date_folder / "Metadata" / "objects_found.json"
    lost_path = base / "Detections" / date_folder / "Metadata" / "objects_lost.json"
    json_mtime = _file_mtime_sum(found_path, lost_path)
    day_key = _day_cache_key(base, date_folder, run_id)
    cached = DAY_CAMERA_INDEX_CACHE.get(day_key)
    if cached and _index_cache_valid(cached[0], cached[1], json_mtime, date_folder):
        return cached[2]

    camera_meta: dict[str, tuple[int | None, set[str]]] = {}
    for camera in cameras:
        cam = str(camera).strip()
        if not cam:
            continue
        sid = _resolve_source_id(params, cam, None)
        camera_meta[cam] = (sid, source_aliases(params, cam, sid))

    by_camera: dict[str, list[dict[str, Any]]] = {cam: [] for cam in camera_meta}
    for obj in _read_json_objects(found_path):
        for cam, (sid, aliases) in camera_meta.items():
            if not _record_matches_camera(obj, aliases=aliases, source_id=sid):
                continue
            item = _detection_index_item(obj, "found", camera=cam, date_folder=date_folder)
            if item:
                by_camera[cam].append(item)
    for obj in _read_json_objects(lost_path):
        for cam, (sid, aliases) in camera_meta.items():
            if not _record_matches_camera(obj, aliases=aliases, source_id=sid):
                continue
            item = _detection_index_item(obj, "lost", camera=cam, date_folder=date_folder)
            if item:
                by_camera[cam].append(item)
    for cam in by_camera:
        by_camera[cam].sort(key=lambda row: row["ts"])
        sid = camera_meta[cam][0]
        per_cam_key = _index_cache_key(base, date_folder, cam, sid)
        DETECTION_INDEX_CACHE[per_cam_key] = (json_mtime, time.time(), by_camera[cam])

    DAY_CAMERA_INDEX_CACHE[day_key] = (json_mtime, time.time(), by_camera)
    return by_camera


def load_detection_index(
    *,
    camera: str,
    date_folder: str,
    run_id: int | None = None,
    source_id: int | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    ticks_only: bool = False,
) -> list[dict[str, Any]]:
    params = _load_params_for_run(run_id)
    base = _playback_data_dir(params)
    items = _load_camera_index_items(
        base=base,
        date_folder=date_folder,
        camera=camera,
        params=params,
        source_id=source_id,
    )
    return _filter_index_window(items, from_ts, to_ts, ticks_only=ticks_only)


def load_detection_index_batch(
    *,
    cameras: list[str],
    date_folder: str,
    run_id: int | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
    ticks_only: bool = False,
) -> dict[str, list[dict[str, Any]]]:
    params = _load_params_for_run(run_id)
    base = _playback_data_dir(params)
    cam_list = [str(camera).strip() for camera in cameras if str(camera).strip()]
    if not cam_list:
        return {}
    all_by_camera = _load_day_index_by_camera(
        base=base,
        date_folder=date_folder,
        run_id=run_id,
        params=params,
        cameras=cam_list,
    )
    by_camera: dict[str, list[dict[str, Any]]] = {}
    for cam in cam_list:
        by_camera[cam] = _filter_index_window(
            all_by_camera.get(cam, []),
            from_ts,
            to_ts,
            ticks_only=ticks_only,
        )
    return by_camera


def match_detections_at(
    items: list[dict[str, Any]],
    target_ts: float,
    match_sec: float = DEFAULT_MATCH_SEC,
) -> list[dict[str, Any]]:
    return [it for it in items if abs(it["ts"] - target_ts) < match_sec]


def nearest_detection_ts(items: list[dict[str, Any]], target_ts: float) -> float | None:
    if not items:
        return None
    best: float | None = None
    best_dist = float("inf")
    for row in items:
        ts = float(row["ts"])
        dist = abs(ts - target_ts)
        if dist < best_dist:
            best_dist = dist
            best = ts
    return best


def _bbox_components(bbox: Any) -> tuple[float, float, float, float] | None:
    if isinstance(bbox, dict):
        try:
            return (
                float(bbox["x"]),
                float(bbox["y"]),
                float(bbox["width"]),
                float(bbox["height"]),
            )
        except (KeyError, TypeError, ValueError):
            return None
    if isinstance(bbox, (list, tuple)) and len(bbox) >= 4:
        try:
            return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))
        except (TypeError, ValueError):
            return None
    return None


def _lerp_bbox(found_bbox: Any, lost_bbox: Any, t: float) -> Any:
    start = _bbox_components(found_bbox)
    end = _bbox_components(lost_bbox)
    if start is None:
        return found_bbox
    if end is None:
        return found_bbox
    t = max(0.0, min(1.0, float(t)))
    vals = [start[i] + (end[i] - start[i]) * t for i in range(4)]
    if isinstance(found_bbox, dict):
        return {"x": vals[0], "y": vals[1], "width": vals[2], "height": vals[3]}
    return vals


def _earliest_by_oid(
    records: list[dict[str, Any]],
    kind: str,
    aliases: set[str],
    source_id: int | None,
    *,
    camera: str | None = None,
    date_folder: str | None = None,
) -> dict[Any, tuple[datetime, dict[str, Any]]]:
    by_oid: dict[Any, tuple[datetime, dict[str, Any]]] = {}
    for obj in records:
        oid = obj.get("object_id")
        if oid is None:
            continue
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            continue
        event_ts = _detection_event_ts(obj, kind, camera=camera, date_folder=date_folder)
        if not event_ts:
            continue
        prev = by_oid.get(oid)
        if prev is None or event_ts < prev[0]:
            by_oid[oid] = (event_ts, obj)
    return by_oid


def _index_item_to_raw(item: dict[str, Any]) -> dict[str, Any]:
    bbox = item.get("bounding_box")
    return {
        "object_id": item.get("object_id"),
        "source_name": item.get("source_name"),
        "source_id": item.get("source_id"),
        "bounding_box": bbox,
        "box": bbox,
        "frame_id": item.get("frame_id"),
        "class_name": item.get("class_name"),
        "confidence": item.get("confidence"),
        "class_id": item.get("class_id"),
        "track_id": item.get("track_id"),
        "global_id": item.get("global_id"),
    }


def _pair_track_intervals(items: list[dict[str, Any]]) -> list[tuple[float, float, dict[str, Any], dict[str, Any]]]:
    by_oid: dict[Any, list[dict[str, Any]]] = {}
    for item in items:
        oid = item.get("object_id")
        if oid is None:
            continue
        by_oid.setdefault(oid, []).append(item)

    intervals: list[tuple[float, float, dict[str, Any], dict[str, Any]]] = []
    for events in by_oid.values():
        events.sort(key=lambda row: float(row["ts"]))
        pending_found: tuple[float, dict[str, Any]] | None = None
        for ev in events:
            kind = str(ev.get("kind") or "")
            if kind == "found":
                pending_found = (float(ev["ts"]), ev)
            elif kind == "lost" and pending_found is not None:
                found_ts, found_ev = pending_found
                lost_ts = float(ev["ts"])
                if lost_ts >= found_ts:
                    intervals.append(
                        (found_ts, lost_ts, _index_item_to_raw(found_ev), _index_item_to_raw(ev))
                    )
                pending_found = None
    return intervals


def _earliest_index_by_oid(
    items: list[dict[str, Any]],
    kind: str,
) -> dict[Any, tuple[float, dict[str, Any]]]:
    by_oid: dict[Any, tuple[float, dict[str, Any]]] = {}
    for item in items:
        if item.get("kind") != kind:
            continue
        oid = item.get("object_id")
        if oid is None:
            continue
        ts = float(item["ts"])
        prev = by_oid.get(oid)
        if prev is None or ts < prev[0]:
            by_oid[oid] = (ts, _index_item_to_raw(item))
    return by_oid


def _load_objects_from_detection_index(
    *,
    target: datetime,
    camera: str,
    date_folder: str,
    source_id: int | None,
    window_sec: float,
) -> list[dict[str, Any]]:
    """Use cached detection index instead of re-parsing every JSON row."""
    items = load_detection_index(
        camera=camera,
        date_folder=date_folder,
        source_id=source_id,
    )
    target_ts = target.timestamp()
    matched = match_detections_at(items, target_ts, window_sec)

    selected: dict[Any, dict[str, Any]] = {}
    snapshot_oids: set[Any] = set()
    for item in matched:
        oid = item.get("object_id")
        kind = str(item.get("kind") or "found")
        key = (kind, oid if oid is not None else id(item))
        selected[key] = _index_item_to_raw(item)
        if oid is not None:
            snapshot_oids.add(oid)

    for found_ts, lost_ts, found_obj, lost_obj in _pair_track_intervals(items):
        oid = found_obj.get("object_id")
        if oid is None or oid in snapshot_oids:
            continue
        if not (found_ts <= target_ts <= lost_ts):
            continue
        span = lost_ts - found_ts
        if span > MAX_LERP_SEC:
            continue
        # Step-hold: keep found bbox until lost (no interpolation).
        selected[("interval", oid)] = dict(found_obj)

    return list(selected.values())


def _load_objects_from_json(
    detections_dir: Path,
    target: datetime,
    aliases: set[str],
    source_id: int | None,
    window_sec: float,
    *,
    camera: str | None = None,
    date_folder: str | None = None,
) -> list[dict[str, Any]]:
    """Load snapshots near ``target``, plus step-held tracks between found and lost."""
    if camera and date_folder:
        return _load_objects_from_detection_index(
            target=target,
            camera=camera,
            date_folder=date_folder,
            source_id=source_id,
            window_sec=window_sec,
        )

    found_path = detections_dir / "objects_found.json"
    lost_path = detections_dir / "objects_lost.json"
    found_list = _read_json_objects(found_path)
    lost_list = _read_json_objects(lost_path)

    selected: dict[Any, dict[str, Any]] = {}
    snapshot_oids: set[Any] = set()

    def consider_snapshot(obj: dict[str, Any], kind: str) -> None:
        event_ts = _detection_event_ts(obj, kind, camera=camera, date_folder=date_folder)
        if not event_ts or abs((event_ts - target).total_seconds()) >= window_sec:
            return
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            return
        oid = obj.get("object_id")
        key = (kind, oid if oid is not None else id(obj))
        selected[key] = obj
        if oid is not None:
            snapshot_oids.add(oid)

    for obj in found_list:
        consider_snapshot(obj, "found")
    for obj in lost_list:
        consider_snapshot(obj, "lost")

    found_by_oid = _earliest_by_oid(
        found_list, "found", aliases, source_id, camera=camera, date_folder=date_folder
    )
    lost_by_oid = _earliest_by_oid(
        lost_list, "lost", aliases, source_id, camera=camera, date_folder=date_folder
    )
    for oid, (found_ts, found_obj) in found_by_oid.items():
        if oid in snapshot_oids:
            continue
        lost_entry = lost_by_oid.get(oid)
        if lost_entry is None:
            continue
        lost_ts, lost_obj = lost_entry
        if not (found_ts <= target <= lost_ts):
            continue
        span = (lost_ts - found_ts).total_seconds()
        if span > MAX_LERP_SEC:
            continue
        # Step-hold: keep found bbox until lost (no interpolation).
        selected[("interval", oid)] = dict(found_obj)

    return list(selected.values())


def _load_events_from_json(
    events_dir: Path,
    target: datetime,
    aliases: set[str],
    source_id: int | None,
    window_sec: float,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for filename, event_type in _EVENT_FILES.items():
        filepath = events_dir / filename
        if not filepath.is_file():
            continue
        try:
            data = json.loads(filepath.read_text(encoding="utf-8"))
        except Exception:
            continue
        events_list = data if isinstance(data, list) else data.get("events", [])
        if not isinstance(events_list, list):
            continue
        for event in events_list:
            if not isinstance(event, dict):
                continue
            event = dict(event)
            event["event_type"] = event_type
            event_timestamp = parse_event_timestamp(event.get("ts") or event.get("time_stamp") or event.get("timestamp"))
            if not event_timestamp:
                continue
            if abs((event_timestamp - target).total_seconds()) >= window_sec:
                continue
            if not _record_matches_camera(event, aliases=aliases, source_id=source_id):
                continue
            events.append(event)
    return events


def _normalize_trail_points(
    trail: Any,
    *,
    img_w: int,
    img_h: int,
) -> list[list[float]]:
    if not isinstance(trail, list) or not trail:
        return []
    points: list[list[float]] = []
    for item in trail:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            x, y = float(item[0]), float(item[1])
        except Exception:
            continue
        if img_w > 0 and img_h > 0 and max(abs(x), abs(y)) > 1.5:
            x /= float(img_w)
            y /= float(img_h)
        points.append([x, y])
    return points


def _serialize_trail_from_raw(
    raw: dict[str, Any],
    *,
    img_w: int,
    img_h: int,
) -> list[list[float]]:
    trail = raw.get("trail") or raw.get("history")
    return _normalize_trail_points(trail, img_w=img_w, img_h=img_h)


def _serialize_object_from_raw(
    raw: dict[str, Any],
    *,
    img_w: int,
    img_h: int,
    event_active: bool = False,
) -> dict[str, Any] | None:
    bbox = raw.get("bounding_box") or raw.get("box")
    if not bbox:
        box, _zone = EventMetadataExtractor.get_bbox_and_zone(raw, False)
        bbox = box
    norm_bbox = EventMetadataExtractor.normalize_bbox_for_display(bbox, img_w, img_h)
    if not norm_bbox:
        return None

    object_id = raw.get("object_id")
    track_id = raw.get("track_id")
    if track_id is None and object_id is not None:
        track_id = object_id

    attributes: list[dict[str, Any]] = []
    raw_attrs = raw.get("attributes")
    if isinstance(raw_attrs, dict):
        for name, data in list(raw_attrs.items())[:4]:
            if isinstance(data, dict):
                attributes.append(
                    {
                        "name": str(name),
                        "state": str(data.get("state", "none")),
                        "confidence": float(data.get("confidence_smooth", data.get("confidence", 0.0)) or 0.0),
                    }
                )
    elif isinstance(raw_attrs, list):
        for item in raw_attrs[:4]:
            if isinstance(item, dict) and item.get("name"):
                attributes.append(
                    {
                        "name": str(item["name"]),
                        "state": str(item.get("state", "none")),
                        "confidence": float(item.get("confidence", 0.0) or 0.0),
                    }
                )

    return {
        "object_id": object_id,
        "global_id": raw.get("global_id"),
        "track_id": track_id,
        "class_id": raw.get("class_id"),
        "class_name": raw.get("class_name"),
        "conf": float(raw.get("confidence", raw.get("conf", 0.0)) or 0.0) if raw.get("confidence") is not None or raw.get("conf") is not None else None,
        "bbox": norm_bbox,
        "event_active": event_active,
        "attributes": attributes,
        "trail": _serialize_trail_from_raw(raw, img_w=img_w, img_h=img_h),
    }


def _event_label(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or event.get("event_name") or "Event")
    object_id = event.get("object_id")
    suffix = f" [{object_id}]" if object_id is not None else ""
    name = event.get("event_name") or event.get("attribute_name") or event.get("zone_name") or event_type
    return f"{name}{suffix}"


def _is_signal_event(event: dict[str, Any]) -> bool:
    event_type = str(event.get("event_type") or "")
    return any(token in event_type for token in ("zone_events", "attribute_events", "zone_entered", "zone_left", "attr_", "ZoneEvent", "AttributeEvent"))


def _row_in_time_window(row: dict[str, Any], target: datetime, window_sec: float) -> bool:
    ts = parse_event_timestamp(row.get("ts") or row.get("time_stamp") or row.get("timestamp"))
    if not ts:
        return False
    return abs((ts - target).total_seconds()) < window_sec


def _load_objects_from_db(
    target: datetime,
    source_name: str,
    date_folder: str,
    window_sec: float,
) -> list[dict[str, Any]]:
    from evileye.api.core.journal_service import _db_controller, _make_db_source

    controller = _db_controller()
    if controller is None:
        return []
    source = _make_db_source(controller, journal_type="objects", date=date_folder)
    rows = source.fetch(0, 500, {"source_name": source_name}, [])
    objects: list[dict[str, Any]] = []
    for row in rows:
        if not _row_in_time_window(row, target, window_sec):
            continue
        objects.append(
            {
                "object_id": row.get("object_id"),
                "class_id": row.get("class_id"),
                "class_name": row.get("class_name"),
                "confidence": row.get("confidence"),
                "bounding_box": row.get("bounding_box"),
                "source_name": row.get("source_name") or source_name,
                "ts": row.get("ts"),
            }
        )
    return objects


def _load_events_from_db(
    target: datetime,
    source_name: str,
    date_folder: str,
    window_sec: float,
) -> list[dict[str, Any]]:
    from evileye.api.core.journal_service import _db_controller, _make_db_source

    controller = _db_controller()
    if controller is None:
        return []
    source = _make_db_source(controller, journal_type="events", date=date_folder)
    rows = source.fetch(0, 500, {"source_name": source_name}, [])
    events: list[dict[str, Any]] = []
    for row in rows:
        if not _row_in_time_window(row, target, window_sec):
            continue
        event = dict(row)
        mapped = str(event.get("event_type") or "")
        if mapped == "ZoneEvent":
            event["event_type"] = "zone_events_entered"
        elif mapped == "AttributeEvent":
            event["event_type"] = "attribute_events_found"
        events.append(event)
    return events


def _db_available() -> bool:
    from evileye.api.core.journal_service import _db_controller

    controller = _db_controller()
    if controller is None:
        return False
    try:
        return bool(controller.is_connected())
    except Exception:
        return False


def _load_json_dynamic_records(
    *,
    target: datetime,
    camera: str,
    date_folder: str,
    window_sec: float,
    params: dict[str, Any],
    aliases: set[str],
    source_id: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    base = _playback_data_dir(params)
    detections_dir = base / "Detections" / date_folder / "Metadata"
    events_dir = base / "Events" / date_folder / "Metadata"
    raw_objects: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    if detections_dir.is_dir():
        raw_objects = _load_objects_from_json(
            detections_dir,
            target,
            aliases,
            source_id,
            window_sec,
            camera=camera,
            date_folder=date_folder,
        )
    if events_dir.is_dir():
        raw_events = _load_events_from_json(
            events_dir, target, aliases, source_id, window_sec,
        )
    return raw_objects, raw_events


def _load_dynamic_records(
    *,
    target: datetime,
    camera: str,
    date_folder: str,
    window_sec: float,
    params: dict[str, Any],
    source_id: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    mode = _playback_storage_mode(params)
    aliases = source_aliases(params, camera, source_id)
    if mode == "database" and _db_available():
        db_objects = _load_objects_from_db(target, camera, date_folder, window_sec)
        db_events = _load_events_from_db(target, camera, date_folder, window_sec)
        if db_objects:
            return db_objects, db_events
        json_objects, json_events = _load_json_dynamic_records(
            target=target,
            camera=camera,
            date_folder=date_folder,
            window_sec=window_sec,
            params=params,
            aliases=aliases,
            source_id=source_id,
        )
        if db_events:
            return json_objects, db_events
        return json_objects, json_events
    return _load_json_dynamic_records(
        target=target,
        camera=camera,
        date_folder=date_folder,
        window_sec=window_sec,
        params=params,
        aliases=aliases,
        source_id=source_id,
    )


def _visualizer_cfg(params: dict[str, Any]) -> dict[str, Any]:
    vis = params.get("visualization") or params.get("visualizer") or {}
    return vis if isinstance(vis, dict) else {}


def _debug_info_from_params(params: dict[str, Any]) -> dict[str, Any]:
    """Runtime-like debug_info.detectors tree from static pipeline config."""
    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    detectors = pipeline.get("detectors") if isinstance(pipeline, dict) else None
    if not isinstance(detectors, list):
        return {}
    mapped: dict[str, Any] = {}
    for idx, detector in enumerate(detectors):
        if isinstance(detector, dict):
            mapped[f"detector_{idx}"] = detector
    return {"detectors": mapped} if mapped else {}


def _resolve_coord_context(
    params: dict[str, Any],
    camera: str,
    source_id: int | None,
    frame_w: int | None,
    frame_h: int | None,
) -> PlaybackCoordContext:
    return resolve_playback_coord_context(
        params,
        camera=camera,
        source_id=source_id,
        frame_w=frame_w,
        frame_h=frame_h,
    )


def _finalize_metadata_payload(payload: dict[str, Any], ctx: PlaybackCoordContext) -> dict[str, Any]:
    payload["coord_ref"] = {"w": ctx.logical_w, "h": ctx.logical_h}
    payload.setdefault("source_id", ctx.source_id)
    return payload


def build_playback_static_metadata(
    *,
    camera: str,
    run_id: int | None = None,
    source_id: int | None = None,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> dict[str, Any]:
    """Config-derived overlay layers (zones, detector ROI) — same serializer as live preview."""
    params = _load_params_for_run(run_id)
    ctx = _resolve_coord_context(params, camera, source_id, frame_w, frame_h)
    img_w, img_h = ctx.logical_w, ctx.logical_h

    vis_cfg = _visualizer_cfg(params)
    show_zones = vis_cfg.get("show_zones")
    if show_zones is None:
        show_zones = vis_cfg.get("display_zones", True)
    show_debug = bool(vis_cfg.get("show_debug_info", False))

    zones_raw: list[Any] = []
    if ctx.source_id is not None:
        zones_raw = extract_zones_by_source(params).get(ctx.source_id, [])

    context = PreviewRenderContext(
        source_name=camera,
        zones=zones_raw,
        debug_info=_debug_info_from_params(params),
        show_zones=bool(show_zones),
        show_debug_info=show_debug,
        show_boxes=False,
        burn_in_overlay=False,
    )
    payload = serialize_preview_metadata(
        context,
        (img_h, img_w),
        source_id=ctx.source_id,
    )
    overlay = payload.get("overlay")
    if not isinstance(overlay, dict):
        overlay = {}
        payload["overlay"] = overlay
    overlay["source_name"] = camera
    return _finalize_metadata_payload(payload, ctx)


def build_playback_metadata(
    *,
    camera: str,
    ts: float,
    date: str | None = None,
    run_id: int | None = None,
    window_sec: float = DEFAULT_MATCH_SEC,
    source_id: int | None = None,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> dict[str, Any]:
    params = _load_params_for_run(run_id)
    ctx = _resolve_coord_context(params, camera, source_id, frame_w, frame_h)
    img_w, img_h = ctx.logical_w, ctx.logical_h

    target = datetime.fromtimestamp(float(ts))
    date_folder = target.strftime("%Y-%m-%d")

    raw_objects, raw_events = _load_dynamic_records(
        target=target,
        camera=camera,
        date_folder=date_folder,
        window_sec=window_sec,
        params=params,
        source_id=ctx.source_id,
    )

    active_object_ids = {
        int(ev["object_id"])
        for ev in raw_events
        if ev.get("object_id") is not None and _is_signal_event(ev)
    }

    objects: list[dict[str, Any]] = []
    seen_keys: set[tuple[Any, ...]] = set()
    for raw in raw_objects:
        oid = raw.get("object_id")
        key = ("obj", oid, tuple(raw.get("bounding_box") or raw.get("box") or ()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        serialized = _serialize_object_from_raw(
            raw,
            img_w=img_w,
            img_h=img_h,
            event_active=oid in active_object_ids if oid is not None else False,
        )
        if serialized:
            objects.append(serialized)

    for event in raw_events:
        if not _is_signal_event(event):
            continue
        box, _zone = EventMetadataExtractor.get_bbox_and_zone(event, False)
        if not box:
            continue
        oid = event.get("object_id")
        key = ("ev", oid, tuple(box if isinstance(box, (list, tuple)) else ()))
        if key in seen_keys:
            continue
        seen_keys.add(key)
        serialized = _serialize_object_from_raw(
            {**event, "bounding_box": box},
            img_w=img_w,
            img_h=img_h,
            event_active=True,
        )
        if serialized:
            objects.append(serialized)

    signal_events = [ev for ev in raw_events if _is_signal_event(ev)]
    event_labels = [_event_label(ev) for ev in signal_events[:8]]

    time_label = target.strftime("%H:%M:%S")
    payload = {
        "source_id": ctx.source_id,
        "ts": float(ts),
        "objects": objects,
        "zones": [],
        "signalization": bool(event_labels),
        "event_labels": event_labels,
        "event_color": [255, 0, 0],
        "debug_rois": [],
        "overlay": {
            "source_name": camera,
            "time_label": time_label,
        },
    }
    return _finalize_metadata_payload(payload, ctx)


def build_playback_metadata_batch(
    *,
    cameras: list[str],
    ts: float,
    date: str | None = None,
    run_id: int | None = None,
    window_sec: float = DEFAULT_MATCH_SEC,
    static_only: bool = False,
    frame_w: int | None = None,
    frame_h: int | None = None,
) -> dict[str, dict[str, Any]]:
    by_camera: dict[str, dict[str, Any]] = {}
    for camera in cameras:
        cam = str(camera).strip()
        if not cam:
            continue
        if static_only:
            by_camera[cam] = build_playback_static_metadata(
                camera=cam,
                run_id=run_id,
                frame_w=frame_w,
                frame_h=frame_h,
            )
        else:
            by_camera[cam] = build_playback_metadata(
                camera=cam,
                ts=ts,
                date=date,
                run_id=run_id,
                window_sec=window_sec,
                frame_w=frame_w,
                frame_h=frame_h,
            )
    return by_camera
