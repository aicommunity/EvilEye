"""Build StreamMetadata-compatible overlay payloads for archive playback."""

from __future__ import annotations

import json
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
    obj_source = raw.get("source_name") or raw.get("source")
    if obj_source and str(obj_source) in aliases:
        return True
    raw_sid = raw.get("source_id")
    if source_id is not None and raw_sid is not None:
        try:
            return int(raw_sid) == int(source_id)
        except Exception:
            pass
    return not obj_source


def _record_event_time(raw: dict[str, Any]) -> datetime | None:
    for key in ("timestamp", "detected_timestamp", "ts", "time_stamp", "lost_timestamp"):
        ts = parse_event_timestamp(raw.get(key))
        if ts:
            return ts
    return None


def _read_json_objects(filepath: Path) -> list[dict[str, Any]]:
    if not filepath.is_file():
        return []
    try:
        data = json.loads(filepath.read_text(encoding="utf-8"))
    except Exception:
        return []
    objects_list = data if isinstance(data, list) else data.get("objects", [])
    return [obj for obj in objects_list if isinstance(obj, dict)]


def _lost_times_by_object_id(lost_objects: list[dict[str, Any]]) -> dict[Any, datetime]:
    lost_map: dict[Any, datetime] = {}
    for obj in lost_objects:
        oid = obj.get("object_id")
        if oid is None:
            continue
        lost_ts = parse_event_timestamp(obj.get("lost_timestamp") or obj.get("timestamp"))
        if lost_ts:
            lost_map[oid] = lost_ts
    return lost_map


def _object_visible_at(
    found: dict[str, Any],
    target: datetime,
    lost_map: dict[Any, datetime],
    window_sec: float,
) -> bool:
    found_ts = parse_event_timestamp(
        found.get("timestamp") or found.get("detected_timestamp") or found.get("ts") or found.get("time_stamp")
    )
    if not found_ts:
        return False
    if abs((found_ts - target).total_seconds()) < window_sec:
        return True
    if found_ts > target:
        return False
    oid = found.get("object_id")
    lost_ts = lost_map.get(oid) if oid is not None else None
    if lost_ts is not None:
        return found_ts <= target <= lost_ts
    return False


def _load_objects_from_json(
    detections_dir: Path,
    target: datetime,
    aliases: set[str],
    source_id: int | None,
    window_sec: float,
) -> list[dict[str, Any]]:
    """Load archive objects active at ``target`` (found..lost) plus in-window snapshots."""
    found_path = detections_dir / "objects_found.json"
    lost_path = detections_dir / "objects_lost.json"
    found_list = _read_json_objects(found_path)
    lost_list = _read_json_objects(lost_path)
    lost_map = _lost_times_by_object_id(lost_list)

    selected: dict[Any, dict[str, Any]] = {}
    for obj in found_list:
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            continue
        oid = obj.get("object_id")
        key = oid if oid is not None else id(obj)
        if _object_visible_at(obj, target, lost_map, window_sec):
            selected[key] = obj

    for obj in lost_list:
        if not _record_matches_camera(obj, aliases=aliases, source_id=source_id):
            continue
        lost_ts = parse_event_timestamp(obj.get("lost_timestamp"))
        if not lost_ts or abs((lost_ts - target).total_seconds()) >= window_sec:
            continue
        oid = obj.get("object_id")
        key = oid if oid is not None else id(obj)
        if key not in selected:
            selected[key] = obj

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
        return (
            _load_objects_from_db(target, camera, date_folder, window_sec),
            _load_events_from_db(target, camera, date_folder, window_sec),
        )
    base = _playback_data_dir(params)
    detections_dir = base / "Detections" / date_folder / "Metadata"
    events_dir = base / "Events" / date_folder / "Metadata"
    raw_objects: list[dict[str, Any]] = []
    raw_events: list[dict[str, Any]] = []
    if detections_dir.is_dir():
        raw_objects = _load_objects_from_json(
            detections_dir, target, aliases, source_id, window_sec,
        )
    if events_dir.is_dir():
        raw_events = _load_events_from_json(
            events_dir, target, aliases, source_id, window_sec,
        )
    return raw_objects, raw_events


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
    window_sec: float = 1.0,
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
    window_sec: float = 1.0,
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
