"""On-disk compact timeline indexes for playback (cache-on-access)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

INDEX_VERSION = 1
TODAY_REBUILD_SEC = 45.0


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    tmp.write_text(raw, encoding="utf-8")
    os.replace(tmp, path)


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _dir_mtime_sig(root: Path, patterns: tuple[str, ...]) -> float:
    if not root.is_dir():
        return 0.0
    total = 0.0
    try:
        for pattern in patterns:
            for path in root.glob(pattern):
                try:
                    total += path.stat().st_mtime
                except OSError:
                    continue
    except OSError:
        return total
    return total


def _is_today(date_folder: str) -> bool:
    from datetime import datetime

    return date_folder == datetime.now().strftime("%Y-%m-%d")


def segment_index_path(streams_date_dir: Path) -> Path:
    return streams_date_dir / "_timeline_segments.json"


def detection_ticks_path(detections_meta_dir: Path) -> Path:
    return detections_meta_dir / "detection_ticks.json"


def event_intervals_path(events_meta_dir: Path) -> Path:
    return events_meta_dir / "event_intervals.json"


def _index_fresh(path: Path, source_mtime: float, date_folder: str) -> dict[str, Any] | None:
    data = _read_json(path)
    if not data or int(data.get("version") or 0) != INDEX_VERSION:
        return None
    stored = float(data.get("source_mtime") or 0.0)
    if abs(stored - source_mtime) > 1e-3:
        if not (_is_today(date_folder) and (time.time() - float(data.get("built_at") or 0.0)) < TODAY_REBUILD_SEC):
            return None
        # Today soft TTL: still accept briefly even if mtime drifted.
        if not _is_today(date_folder):
            return None
    return data


def read_segment_index_if_fresh(date_folder: str) -> dict[str, list[dict[str, Any]]] | None:
    from evileye.api.core import playback_service as svc

    streams_dir = svc.data_dir() / "Streams" / date_folder
    index_path = segment_index_path(streams_dir)
    source_mtime = _dir_mtime_sig(streams_dir, ("**/*.mp4", "**/*.session.json"))
    cached = _index_fresh(index_path, source_mtime, date_folder)
    if cached is None:
        return None
    by_camera = cached.get("by_camera") or {}
    if not isinstance(by_camera, dict):
        return None
    return {str(k): list(v or []) for k, v in by_camera.items()}


def upsert_segment_index_camera(
    date_folder: str,
    camera: str,
    rows: list[dict[str, Any]],
) -> None:
    from evileye.api.core import playback_service as svc

    streams_dir = svc.data_dir() / "Streams" / date_folder
    index_path = segment_index_path(streams_dir)
    source_mtime = _dir_mtime_sig(streams_dir, ("**/*.mp4", "**/*.session.json"))
    existing = _read_json(index_path) or {
        "version": INDEX_VERSION,
        "date": date_folder,
        "by_camera": {},
    }
    by_camera = existing.get("by_camera") if isinstance(existing.get("by_camera"), dict) else {}
    by_camera[camera] = rows
    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "by_camera": by_camera,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to upsert segment index %s: %s", index_path, exc)


def ensure_segment_index(
    *,
    date_folder: str,
    cameras: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build or load Streams/{date}/_timeline_segments.json."""
    from evileye.api.core import playback_service as svc

    streams_dir = svc.data_dir() / "Streams" / date_folder
    index_path = segment_index_path(streams_dir)
    source_mtime = _dir_mtime_sig(streams_dir, ("**/*.mp4", "**/*.session.json"))
    cached = _index_fresh(index_path, source_mtime, date_folder)
    if cached is not None:
        by_camera = cached.get("by_camera") or {}
        if isinstance(by_camera, dict):
            if cameras:
                return {cam: list(by_camera.get(cam) or []) for cam in cameras if cam}
            return {str(k): list(v or []) for k, v in by_camera.items()}

    # Discover cameras under the day folder when none requested.
    cam_list = [c for c in (cameras or []) if c]
    if not cam_list and streams_dir.is_dir():
        try:
            discovered = svc.discover_cameras(date_folder)
            cam_list = [str(item.get("id") or item.get("name") or "").strip() for item in discovered]
            cam_list = [c for c in cam_list if c]
        except Exception:
            cam_list = []

    by_camera: dict[str, list[dict[str, Any]]] = {}
    existing = _read_json(index_path) or {}
    prev = existing.get("by_camera") if isinstance(existing.get("by_camera"), dict) else {}
    for cam, rows in prev.items():
        by_camera[str(cam)] = list(rows or [])

    for cam in cam_list:
        try:
            by_camera[cam] = svc.load_segments_uncached(cam, date=date_folder)
        except Exception as exc:
            logger.debug("segment index build failed for %s: %s", cam, exc)
            by_camera[cam] = []

    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "by_camera": by_camera,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to write segment index %s: %s", index_path, exc)
    if cameras:
        return {cam: list(by_camera.get(cam) or []) for cam in cameras if cam}
    return by_camera


def filter_segments_window(
    items: list[dict[str, Any]],
    from_ts: float | None,
    to_ts: float | None,
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in items:
        start = float(row.get("start_ts") or 0.0)
        end = float(row.get("end_ts") or 0.0)
        if from_ts is not None and end < from_ts:
            continue
        if to_ts is not None and start > to_ts:
            continue
        out.append(row)
    return out


def ensure_detection_ticks(
    *,
    date_folder: str,
    cameras: list[str],
    run_id: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Build or load Detections/{date}/Metadata/detection_ticks.json."""
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params)
    meta_dir = base / "Detections" / date_folder / "Metadata"
    index_path = detection_ticks_path(meta_dir)
    source_mtime = meta._file_mtime_sum(
        meta_dir / "objects_found.json",
        meta_dir / "objects_lost.json",
    )
    cached = _index_fresh(index_path, source_mtime, date_folder)
    cam_list = [c for c in cameras if c]
    if cached is not None:
        raw_by = cached.get("by_camera") or {}
        out: dict[str, list[dict[str, Any]]] = {}
        for cam in cam_list:
            rows = raw_by.get(cam) or []
            out[cam] = [_tick_row_to_item(row) for row in rows]
        return out

    full = meta.load_detection_index_batch(
        cameras=cam_list,
        date_folder=date_folder,
        run_id=run_id,
        ticks_only=False,
    )
    compact: dict[str, list[list[Any]]] = {}
    result: dict[str, list[dict[str, Any]]] = {}
    for cam, items in full.items():
        compact[cam] = [[float(it["ts"]), it.get("kind"), it.get("object_id")] for it in items]
        result[cam] = [meta._tick_only_item(it) for it in items]

    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "by_camera": compact,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to write detection ticks %s: %s", index_path, exc)
    return result


def _tick_row_to_item(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        return {
            "ts": float(row["ts"]),
            "kind": row.get("kind"),
            "object_id": row.get("object_id"),
        }
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        return {
            "ts": float(row[0]),
            "kind": row[1],
            "object_id": row[2] if len(row) > 2 else None,
        }
    return {"ts": 0.0, "kind": None, "object_id": None}


def ensure_event_intervals(
    *,
    date_folder: str,
    cameras: list[str] | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Build or load Events/{date}/Metadata/event_intervals.json."""
    from evileye.api.core import playback_service as svc

    events_dir = svc.data_dir() / "Events" / date_folder / "Metadata"
    index_path = event_intervals_path(events_dir)
    source_mtime = _dir_mtime_sig(events_dir, ("*.json",))
    cached = _index_fresh(index_path, source_mtime, date_folder)
    if cached is not None:
        items = cached.get("items") or []
        if isinstance(items, list):
            if cameras:
                cam_set = set(cameras)
                return [it for it in items if not it.get("camera") or it.get("camera") in cam_set]
            return list(items)

    items = svc.load_event_intervals(
        None,
        None,
        None,
        cameras,
        date=date_folder,
        limit=limit,
    )
    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "items": items,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to write event intervals %s: %s", index_path, exc)
    return items


def build_timeline(
    *,
    date_folder: str,
    cameras: list[str],
    run_id: int | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
) -> dict[str, Any]:
    cam_list = [c for c in cameras if c]
    segments_by = ensure_segment_index(date_folder=date_folder, cameras=cam_list)
    ticks_by = ensure_detection_ticks(date_folder=date_folder, cameras=cam_list, run_id=run_id)
    events = ensure_event_intervals(date_folder=date_folder, cameras=cam_list)

    by_camera: dict[str, Any] = {}
    for cam in cam_list:
        segs = filter_segments_window(segments_by.get(cam) or [], from_ts, to_ts)
        ticks = ticks_by.get(cam) or []
        if from_ts is not None:
            ticks = [t for t in ticks if float(t["ts"]) >= float(from_ts)]
        if to_ts is not None:
            ticks = [t for t in ticks if float(t["ts"]) <= float(to_ts)]
        cam_events = [
            ev
            for ev in events
            if (ev.get("camera") in (None, cam))
            and (from_ts is None or float(ev.get("end_ts") or 0) >= float(from_ts))
            and (to_ts is None or float(ev.get("start_ts") or 0) <= float(to_ts))
        ]
        by_camera[cam] = {
            "segments": segs,
            "detection_ticks": ticks,
            "events": cam_events,
        }
    return {"date": date_folder, "by_camera": by_camera}
