"""On-disk compact timeline indexes for playback (cache-on-access + SWR)."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from pathlib import Path
from typing import Any, Optional

from evileye.api.core.cache_policy import DEFAULT_CACHE_POLICY
from evileye.api.core.index_repository import project_event_items
from evileye.api.core.singleflight import singleflight

logger = logging.getLogger(__name__)

INDEX_VERSION = 3
# Soft TTL for "today" when source mtime keeps drifting under live capture.
TODAY_REBUILD_SEC = 300.0
# Video continuing this long after the last detection tick ⇒ journal likely stalled.
# Short/medium quiet (empty scene) is normal and must not be painted as a fault.
INFERENCE_STALL_AFTER_LAST_TICK_SEC = 3 * 3600.0

# Re-export policy for diagnostics / tests (T19).
CACHE_POLICY = DEFAULT_CACHE_POLICY


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    ordered = sorted((float(a), float(b)) for a, b in intervals if b > a)
    if not ordered:
        return []
    merged: list[tuple[float, float]] = [ordered[0]]
    for start, end in ordered[1:]:
        prev_start, prev_end = merged[-1]
        if start <= prev_end:
            merged[-1] = (prev_start, max(prev_end, end))
        else:
            merged.append((start, end))
    return merged


def inference_gap_bands(
    segments: list[dict[str, Any]],
    ticks: list[dict[str, Any]],
    *,
    stall_after_last_tick_sec: float = INFERENCE_STALL_AFTER_LAST_TICK_SEC,
) -> list[dict[str, Any]]:
    """Mark only 'journal stalled while video continued' — not quiet no-detection periods.

    For each merged playable continuum that has at least one tick, if recording
    continues more than ``stall_after_last_tick_sec`` past the last tick, emit
    ``[last_tick, continuum_end]``. Mid-session quiet gaps and segments with
    zero ticks are left unmarked (normal empty scene / no objects).
    """
    universe: list[tuple[float, float]] = []
    for seg in segments or []:
        try:
            start = float(seg.get("start_ts"))
            end = float(seg.get("end_ts"))
        except (TypeError, ValueError):
            continue
        if end > start:
            universe.append((start, end))
    if not universe:
        return []

    tick_ts: list[float] = []
    for tick in ticks or []:
        try:
            tick_ts.append(float(tick["ts"] if isinstance(tick, dict) else tick[0]))
        except (TypeError, ValueError, KeyError, IndexError):
            continue
    tick_ts.sort()
    if not tick_ts:
        return []

    stall_need = max(0.0, float(stall_after_last_tick_sec))
    bands: list[dict[str, Any]] = []
    for u_start, u_end in _merge_intervals(universe):
        in_block = [ts for ts in tick_ts if u_start <= ts <= u_end]
        if not in_block:
            continue
        last = in_block[-1]
        if u_end - last < stall_need:
            continue
        bands.append({"from": last, "to": u_end, "kind": "inference_gap"})
    return bands


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


def _dir_mtime_sig(
    root: Path,
    patterns: tuple[str, ...],
    *,
    exclude_names: frozenset[str] | None = None,
) -> float:
    if not root.is_dir():
        return 0.0
    skip = exclude_names or frozenset()
    total = 0.0
    try:
        for pattern in patterns:
            for path in root.glob(pattern):
                if path.name in skip:
                    continue
                try:
                    total += path.stat().st_mtime
                except OSError:
                    continue
    except OSError:
        return total
    return total


_GENERATED_INDEX_NAMES = frozenset(
    {
        "detection_ticks.json",
        "event_intervals.json",
        "_timeline_segments.json",
    }
)


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


_REFRESH_SLOTS = threading.Semaphore(2)


def _schedule_refresh(name: str, key: str, fn) -> None:
    def _job() -> None:
        try:
            singleflight(key, fn)
        except Exception as exc:
            logger.debug("background %s refresh failed: %s", name, exc)
        finally:
            _REFRESH_SLOTS.release()

    # F10: acquire permit before spawning the daemon thread.
    if not _REFRESH_SLOTS.acquire(blocking=False):
        logger.debug("background %s refresh skipped (in-flight cap)", name)
        return
    threading.Thread(target=_job, name=name, daemon=True).start()


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


def read_segment_index_stale(date_folder: str) -> dict[str, list[dict[str, Any]]] | None:
    """Return on-disk segment index even when mtime is stale (SWR fallback)."""
    from evileye.api.core import playback_service as svc

    streams_dir = svc.data_dir() / "Streams" / date_folder
    index_path = segment_index_path(streams_dir)
    data = _read_json(index_path)
    if not data or int(data.get("version") or 0) != INDEX_VERSION:
        return None
    by_camera = data.get("by_camera") or {}
    if not isinstance(by_camera, dict):
        return None
    return {str(k): list(v or []) for k, v in by_camera.items()}


def schedule_segment_index_refresh(date_folder: str, cameras: list[str] | None = None) -> None:
    """Best-effort background rebuild so the next request is fast."""
    cam_list = [c for c in (cameras or []) if c]
    _schedule_refresh(
        f"seg-index-{date_folder}",
        f"ensure_segment_index:{date_folder}",
        lambda: _rebuild_segment_index(date_folder=date_folder, cameras=cam_list or None),
    )


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


def _rebuild_segment_index(
    *,
    date_folder: str,
    cameras: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    from evileye.api.core import playback_service as svc

    streams_dir = svc.data_dir() / "Streams" / date_folder
    index_path = segment_index_path(streams_dir)
    source_mtime = _dir_mtime_sig(streams_dir, ("**/*.mp4", "**/*.session.json"))

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

    stale = read_segment_index_stale(date_folder)
    if stale is not None:
        schedule_segment_index_refresh(date_folder, cameras)
        if cameras:
            return {cam: list(stale.get(cam) or []) for cam in cameras if cam}
        return stale

    return singleflight(
        f"ensure_segment_index:{date_folder}",
        lambda: _rebuild_segment_index(date_folder=date_folder, cameras=cameras),
    )


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


def filter_event_intervals_window(
    items: list[dict[str, Any]],
    from_ts: float | None,
    to_ts: float | None,
) -> list[dict[str, Any]]:
    """Same overlap rule as segments; also accepts point events with only `ts`."""
    out: list[dict[str, Any]] = []
    for row in items:
        if "start_ts" in row or "end_ts" in row:
            start = float(row.get("start_ts") or row.get("ts") or 0.0)
            end = float(row.get("end_ts") or start)
        else:
            start = end = float(row.get("ts") or 0.0)
        if from_ts is not None and end < from_ts:
            continue
        if to_ts is not None and start > to_ts:
            continue
        out.append(row)
    return out


def _ticks_from_payload(data: dict[str, Any], cameras: list[str]) -> dict[str, list[dict[str, Any]]]:
    raw_by = data.get("by_camera") or {}
    out: dict[str, list[dict[str, Any]]] = {}
    for cam in cameras:
        rows = raw_by.get(cam) or []
        out[cam] = [_tick_row_to_item(row) for row in rows]
    return out


def _payload_covers_cameras(data: dict[str, Any], cameras: list[str]) -> bool:
    """True when on-disk index has an entry for every requested camera."""
    if not cameras:
        return True
    raw_by = data.get("by_camera")
    if not isinstance(raw_by, dict):
        # event_intervals: prefer explicit covered_cameras (includes empty cams).
        covered = data.get("covered_cameras")
        if not isinstance(covered, list) or not covered:
            covered = data.get("cameras")
        if isinstance(covered, list) and covered:
            have = {str(c) for c in covered}
            return all(c in have for c in cameras)
        return False
    return all(cam in raw_by for cam in cameras)


def read_detection_ticks_stale(
    date_folder: str,
    cameras: list[str],
    *,
    run_id: int | None = None,
) -> dict[str, list[dict[str, Any]]] | None:
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params)
    meta_dir = base / "Detections" / date_folder / "Metadata"
    index_path = detection_ticks_path(meta_dir)
    data = _read_json(index_path)
    if not data or int(data.get("version") or 0) != INDEX_VERSION:
        return None
    return _ticks_from_payload(data, [c for c in cameras if c])


def schedule_detection_ticks_refresh(
    date_folder: str,
    cameras: list[str],
    *,
    run_id: int | None = None,
) -> None:
    cam_list = [c for c in cameras if c]
    _schedule_refresh(
        f"det-ticks-{date_folder}",
        f"ensure_detection_ticks:{date_folder}:{run_id}",
        lambda: _rebuild_detection_ticks(date_folder=date_folder, cameras=cam_list, run_id=run_id),
    )


def _rebuild_detection_ticks(
    *,
    date_folder: str,
    cameras: list[str],
    run_id: int | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Rebuild compact ticks; reload when source_mtime changes (R04)."""
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params)
    meta_dir = base / "Detections" / date_folder / "Metadata"
    index_path = detection_ticks_path(meta_dir)
    source_mtime = meta._file_mtime_sum(
        meta_dir / "objects_found.json",
        meta_dir / "objects_lost.json",
    )
    cam_list = [c for c in cameras if c]

    existing = _read_json(index_path) or {}
    prev_raw = existing.get("by_camera") if isinstance(existing.get("by_camera"), dict) else {}
    compact: dict[str, list[list[Any]]] = {
        str(k): list(v or []) for k, v in prev_raw.items()
    }

    prev_mtime = existing.get("source_mtime")
    version_ok = int(existing.get("version") or 0) == INDEX_VERSION
    if (not version_ok) or (prev_mtime != source_mtime):
        reload_cams = sorted(set(cam_list) | set(compact.keys()))
    else:
        reload_cams = [c for c in cam_list if c not in compact]

    if reload_cams:
        full = meta._load_day_index_by_camera(
            base=base,
            date_folder=date_folder,
            run_id=run_id,
            params=params,
            cameras=reload_cams,
        )
        for cam in reload_cams:
            items = full.get(cam) or []
            compact[cam] = [_compact_tick_row(it) for it in items]

    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "cameras": sorted(compact.keys()),
        "by_camera": compact,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to write detection ticks %s: %s", index_path, exc)

    # F08: return full day compact→items for all cams in the file (not leader projection).
    result: dict[str, list[dict[str, Any]]] = {}
    for cam, rows in compact.items():
        result[str(cam)] = [_tick_row_to_item(row) for row in (rows or [])]
    return result


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
    cam_list = [c for c in cameras if c]
    cached = _index_fresh(index_path, source_mtime, date_folder)
    if cached is not None and _payload_covers_cameras(cached, cam_list):
        return _ticks_from_payload(cached, cam_list)
    if cached is not None and not _payload_covers_cameras(cached, cam_list):
        # Partial index: merge missing cameras without discarding coverage.
        full = singleflight(
            f"ensure_detection_ticks:{date_folder}:{run_id}:{base}",
            lambda: _rebuild_detection_ticks(date_folder=date_folder, cameras=cam_list, run_id=run_id),
        )
        # After shared build, project this caller's cameras (F08).
        return {c: list(full.get(c) or []) for c in cam_list}

    stale = read_detection_ticks_stale(date_folder, cam_list, run_id=run_id)
    if stale is not None:
        # Only serve stale if it covers requested cams; else rebuild sync.
        stale_path = _read_json(index_path)
        if stale_path is not None and _payload_covers_cameras(stale_path, cam_list):
            schedule_detection_ticks_refresh(date_folder, cam_list, run_id=run_id)
            return stale

    full = singleflight(
        f"ensure_detection_ticks:{date_folder}:{run_id}:{base}",
        lambda: _rebuild_detection_ticks(date_folder=date_folder, cameras=cam_list, run_id=run_id),
    )
    return {c: list(full.get(c) or []) for c in cam_list}


def _compact_tick_row(item: dict[str, Any]) -> list[Any]:
    row: list[Any] = [float(item["ts"]), item.get("kind"), item.get("object_id")]
    preview_path = item.get("preview_path")
    bbox = item.get("bounding_box")
    if preview_path:
        row.append(preview_path)
        if bbox:
            row.append(bbox)
    elif bbox:
        row.append(None)
        row.append(bbox)
    return row


def _tick_row_to_item(row: Any) -> dict[str, Any]:
    if isinstance(row, dict):
        out: dict[str, Any] = {
            "ts": float(row["ts"]),
            "kind": row.get("kind"),
            "object_id": row.get("object_id"),
        }
        if row.get("preview_path"):
            out["preview_path"] = row["preview_path"]
        if row.get("bounding_box"):
            out["bounding_box"] = row["bounding_box"]
        return out
    if isinstance(row, (list, tuple)) and len(row) >= 2:
        out = {
            "ts": float(row[0]),
            "kind": row[1],
            "object_id": row[2] if len(row) > 2 else None,
        }
        if len(row) > 3 and row[3]:
            out["preview_path"] = row[3]
        if len(row) > 4 and row[4]:
            out["bounding_box"] = row[4]
        return out
    return {"ts": 0.0, "kind": None, "object_id": None}


def read_event_intervals_stale(
    date_folder: str,
    cameras: list[str] | None = None,
) -> list[dict[str, Any]] | None:
    from evileye.api.core import playback_service as svc

    events_dir = svc.data_dir() / "Events" / date_folder / "Metadata"
    index_path = event_intervals_path(events_dir)
    data = _read_json(index_path)
    if not data or int(data.get("version") or 0) != INDEX_VERSION:
        return None
    items = data.get("items") or []
    if not isinstance(items, list):
        return None
    if cameras:
        cam_set = set(cameras)
        return [it for it in items if not it.get("camera") or it.get("camera") in cam_set]
    return list(items)


def schedule_event_intervals_refresh(
    date_folder: str,
    cameras: list[str] | None = None,
    *,
    limit: int = 2000,
) -> None:
    cam_list = [c for c in (cameras or []) if c]
    _schedule_refresh(
        f"evt-intervals-{date_folder}",
        f"ensure_event_intervals:{date_folder}",
        lambda: _rebuild_event_intervals(date_folder=date_folder, cameras=cam_list or None, limit=limit),
    )


def _rebuild_event_intervals(
    *,
    date_folder: str,
    cameras: list[str] | None = None,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    """Build full-day event index. Always returns the complete item list (R03/R05)."""
    from evileye.api.core import playback_service as svc

    events_dir = svc.data_dir() / "Events" / date_folder / "Metadata"
    index_path = event_intervals_path(events_dir)
    # A10: exclude generated index from signature so write does not invalidate itself.
    source_mtime = _dir_mtime_sig(
        events_dir,
        ("*.json",),
        exclude_names=_GENERATED_INDEX_NAMES,
    )
    # Uncapped build: presentation limit applies only on HTTP paths.
    items = svc.load_event_intervals(
        None,
        None,
        None,
        None,
        date=date_folder,
        limit=max(int(limit or 2000), 2000),
        presentation_cap=None,
    )
    cam_names = sorted(
        {
            str(it.get("camera") or "").strip()
            for it in items
            if str(it.get("camera") or "").strip()
        }
    )
    requested = {c for c in (cameras or []) if c}
    # F09: persist previous negative coverage for the same source version.
    prev = _read_json(index_path) or {}
    prev_covered = prev.get("covered_cameras") if isinstance(prev.get("covered_cameras"), list) else []
    prev_mtime = prev.get("source_mtime")
    same_version = (
        int(prev.get("version") or 0) == INDEX_VERSION
        and prev_mtime is not None
        and abs(float(prev_mtime) - float(source_mtime)) <= 1e-3
    )
    covered_set = set(cam_names) | requested
    if same_version:
        covered_set |= {str(c) for c in prev_covered if c}
    # System rows are frequently injected for restricted queries.
    if "System" in requested or any(str(it.get("camera") or "") == "System" for it in items):
        covered_set.add("System")
    covered = sorted(covered_set)
    payload = {
        "version": INDEX_VERSION,
        "date": date_folder,
        "built_at": time.time(),
        "source_mtime": source_mtime,
        "cameras": cam_names,
        "covered_cameras": covered,
        "complete": True,
        "items": items,
    }
    try:
        _atomic_write_json(index_path, payload)
    except Exception as exc:
        logger.debug("failed to write event intervals %s: %s", index_path, exc)
    # Never project by caller cameras here — singleflight followers need the full day.
    return list(items)


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
    source_mtime = _dir_mtime_sig(
        events_dir,
        ("*.json",),
        exclude_names=_GENERATED_INDEX_NAMES,
    )
    cam_list = [c for c in (cameras or []) if c]

    def _rebuild_full() -> list[dict[str, Any]]:
        # Pass requested cams only for covered_cameras bookkeeping, not return filter.
        return _rebuild_event_intervals(
            date_folder=date_folder, cameras=cam_list or None, limit=limit
        )

    cached = _index_fresh(index_path, source_mtime, date_folder)
    if cached is not None:
        items = cached.get("items") or []
        if isinstance(items, list):
            if cam_list and not _payload_covers_cameras(cached, cam_list):
                full = singleflight(
                    f"ensure_event_intervals:{date_folder}",
                    _rebuild_full,
                )
                return project_event_items(full, cam_list)
            return project_event_items(items, cam_list)

    stale = read_event_intervals_stale(date_folder, cameras)
    if stale is not None:
        schedule_event_intervals_refresh(date_folder, cameras, limit=limit)
        return stale

    full = singleflight(
        f"ensure_event_intervals:{date_folder}",
        _rebuild_full,
    )
    return project_event_items(full, cam_list)


def build_timeline(
    *,
    date_folder: str,
    cameras: list[str],
    run_id: int | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
) -> dict[str, Any]:
    cam_list = [c for c in cameras if c]
    key = f"timeline:{date_folder}:{run_id}:{','.join(sorted(cam_list))}:{from_ts}:{to_ts}"

    def _build() -> dict[str, Any]:
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
                "bands": inference_gap_bands(segs, ticks),
            }
        return {"date": date_folder, "by_camera": by_camera}

    return singleflight(key, _build)


def build_timeline_segments_only(
    *,
    date_folder: str,
    cameras: list[str],
    run_id: int | None = None,
    from_ts: float | None = None,
    to_ts: float | None = None,
) -> dict[str, Any]:
    """Fast timeline payload: segments only (no journal scans)."""
    cam_list = [c for c in cameras if c]
    key = f"timeline_segments:{date_folder}:{run_id}:{','.join(sorted(cam_list))}:{from_ts}:{to_ts}"

    def _build() -> dict[str, Any]:
        segments_by = ensure_segment_index(date_folder=date_folder, cameras=cam_list)
        by_camera: dict[str, Any] = {}
        for cam in cam_list:
            segs = filter_segments_window(segments_by.get(cam) or [], from_ts, to_ts)
            by_camera[cam] = {
                "segments": segs,
                "detection_ticks": [],
                "events": [],
                "bands": inference_gap_bands(segs, []),
            }
        return {"date": date_folder, "by_camera": by_camera}

    return singleflight(key, _build)
