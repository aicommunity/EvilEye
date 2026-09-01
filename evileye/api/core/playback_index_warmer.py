"""Background warmer for playback on-disk indexes across archive dates."""

from __future__ import annotations

import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

_warm_stop = threading.Event()
_warm_thread: threading.Thread | None = None

_WARM_RECENT_DAYS = int(os.getenv("EVILEYE_PLAYBACK_WARM_RECENT_DAYS", "14") or 14)


def list_detection_dates(*, run_id: int | None = None) -> list[str]:
    """Return YYYY-MM-DD folders under Detections that have journal files."""
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params) / "Detections"
    if not base.is_dir():
        return []
    out: list[str] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        name = path.name
        if len(name) != 10 or name[4] != "-" or name[7] != "-":
            continue
        meta_dir = path / "Metadata"
        if (meta_dir / "objects_found.json").is_file() or (meta_dir / "objects_lost.json").is_file():
            out.append(name)
    return out


def list_stream_dates(*, run_id: int | None = None) -> list[str]:
    """Return YYYY-MM-DD folders under Streams that have recording data."""
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params) / "Streams"
    if not base.is_dir():
        return []
    out: list[str] = []
    for path in sorted(base.iterdir()):
        if not path.is_dir():
            continue
        name = path.name
        if len(name) != 10 or name[4] != "-" or name[7] != "-":
            continue
        if any(path.iterdir()):
            out.append(name)
    return out


def _recent_dates(dates: list[str], *, limit: int = _WARM_RECENT_DAYS) -> list[str]:
    if limit <= 0:
        return list(dates)
    return list(dates)[-limit:]


def _cameras_for_warm(*, run_id: int | None = None) -> list[str]:
    from evileye.api.core.playback_service import list_logical_cameras

    cams = []
    try:
        for row in list_logical_cameras(run_id=run_id):
            name = str(row.get("id") or row.get("source_name") or "").strip()
            if not name or ("-" in name and not row.get("split")):
                if "-" in name and row.get("parent_folder") == name:
                    continue
            if name:
                cams.append(name)
    except Exception as exc:
        logger.debug("list_logical_cameras for warm failed: %s", exc)
    plain = [c for c in cams if "-" not in c]
    return sorted(set(plain or cams))


def _needs_detection_rebuild(date_folder: str, *, run_id: int | None = None) -> bool:
    from evileye.api.core import playback_metadata_service as meta
    from evileye.api.core.playback_timeline_index import (
        INDEX_VERSION,
        TODAY_REBUILD_SEC,
        _index_fresh,
        detection_ticks_path,
        _is_today,
        _read_json,
    )

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params)
    meta_dir = base / "Detections" / date_folder / "Metadata"
    index_path = detection_ticks_path(meta_dir)
    source_mtime = meta._file_mtime_sum(
        meta_dir / "objects_found.json",
        meta_dir / "objects_lost.json",
    )
    fresh = _index_fresh(index_path, source_mtime, date_folder)
    if fresh is not None:
        return False
    data = _read_json(index_path)
    if (
        data
        and int(data.get("version") or 0) == INDEX_VERSION
        and _is_today(date_folder)
        and (time.time() - float(data.get("built_at") or 0.0)) < TODAY_REBUILD_SEC
    ):
        return False
    return True


def _needs_segment_rebuild(date_folder: str) -> bool:
    from evileye.api.core.playback_timeline_index import read_segment_index_if_fresh

    return read_segment_index_if_fresh(date_folder) is None


def _needs_event_rebuild(date_folder: str, cameras: list[str]) -> bool:
    from evileye.api.core.playback_timeline_index import read_event_intervals_stale

    return read_event_intervals_stale(date_folder, cameras) is None


def warm_detection_ticks_for_date(
    date_folder: str,
    *,
    run_id: int | None = None,
    cameras: list[str] | None = None,
) -> str:
    """Build ticks for one date if missing/stale. Returns status: built|skip|fail."""
    from evileye.api.core.playback_timeline_index import _rebuild_detection_ticks
    from evileye.api.core.singleflight import singleflight

    if not _needs_detection_rebuild(date_folder, run_id=run_id):
        return "skip"

    cam_list = list(cameras or _cameras_for_warm(run_id=run_id))
    if not cam_list:
        return "skip"

    t0 = time.time()
    try:
        singleflight(
            f"ensure_detection_ticks:{date_folder}:{run_id}",
            lambda: _rebuild_detection_ticks(date_folder=date_folder, cameras=cam_list, run_id=run_id),
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            "detection_ticks warm date=%s status=built elapsed_ms=%s n_cameras=%s",
            date_folder,
            elapsed_ms,
            len(cam_list),
        )
        return "built"
    except Exception as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "detection_ticks warm date=%s status=fail elapsed_ms=%s err=%s",
            date_folder,
            elapsed_ms,
            exc,
        )
        return "fail"


def warm_segment_index_for_date(
    date_folder: str,
    *,
    cameras: list[str] | None = None,
) -> str:
    from evileye.api.core.playback_timeline_index import _rebuild_segment_index
    from evileye.api.core.singleflight import singleflight

    if not _needs_segment_rebuild(date_folder):
        return "skip"

    cam_list = list(cameras or _cameras_for_warm())
    if not cam_list:
        return "skip"

    t0 = time.time()
    try:
        singleflight(
            f"ensure_segment_index:{date_folder}",
            lambda: _rebuild_segment_index(date_folder=date_folder, cameras=cam_list),
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            "segment_index warm date=%s status=built elapsed_ms=%s n_cameras=%s",
            date_folder,
            elapsed_ms,
            len(cam_list),
        )
        return "built"
    except Exception as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "segment_index warm date=%s status=fail elapsed_ms=%s err=%s",
            date_folder,
            elapsed_ms,
            exc,
        )
        return "fail"


def warm_event_intervals_for_date(
    date_folder: str,
    *,
    cameras: list[str] | None = None,
) -> str:
    from evileye.api.core.playback_timeline_index import _rebuild_event_intervals
    from evileye.api.core.singleflight import singleflight

    cam_list = list(cameras or _cameras_for_warm())
    if not cam_list:
        return "skip"
    if not _needs_event_rebuild(date_folder, cam_list):
        return "skip"

    t0 = time.time()
    try:
        singleflight(
            f"ensure_event_intervals:{date_folder}",
            lambda: _rebuild_event_intervals(date_folder=date_folder, cameras=cam_list),
        )
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.info(
            "event_intervals warm date=%s status=built elapsed_ms=%s n_cameras=%s",
            date_folder,
            elapsed_ms,
            len(cam_list),
        )
        return "built"
    except Exception as exc:
        elapsed_ms = int((time.time() - t0) * 1000)
        logger.warning(
            "event_intervals warm date=%s status=fail elapsed_ms=%s err=%s",
            date_folder,
            elapsed_ms,
            exc,
        )
        return "fail"


def warm_playback_indexes_for_date(
    date_folder: str,
    *,
    run_id: int | None = None,
    cameras: list[str] | None = None,
) -> dict[str, str]:
    cam_list = list(cameras or _cameras_for_warm(run_id=run_id))
    return {
        "segments": warm_segment_index_for_date(date_folder, cameras=cam_list),
        "detection_ticks": warm_detection_ticks_for_date(date_folder, run_id=run_id, cameras=cam_list),
        "event_intervals": warm_event_intervals_for_date(date_folder, cameras=cam_list),
    }


def _warm_loop(run_id: int | None = None) -> None:
    if _warm_stop.wait(8.0):
        return
    try:
        stream_dates = _recent_dates(list_stream_dates(run_id=run_id))
        det_dates = _recent_dates(list_detection_dates(run_id=run_id))
        dates = sorted(set(stream_dates) | set(det_dates))
        cameras = _cameras_for_warm(run_id=run_id)
        logger.info(
            "playback_index warm start dates=%s cameras=%s recent_limit=%s",
            len(dates),
            len(cameras),
            _WARM_RECENT_DAYS,
        )
        for date_folder in dates:
            if _warm_stop.is_set():
                break
            warm_playback_indexes_for_date(date_folder, run_id=run_id, cameras=cameras)
            if _warm_stop.wait(0.25):
                break
        logger.info("playback_index warm finished")
    except Exception as exc:
        logger.warning("playback_index warm aborted: %s", exc)


def start_detection_ticks_warmer(*, run_id: int | None = None) -> None:
    global _warm_thread
    if _warm_thread is not None and _warm_thread.is_alive():
        return
    _warm_stop.clear()
    _warm_thread = threading.Thread(
        target=_warm_loop,
        kwargs={"run_id": run_id},
        daemon=True,
        name="PlaybackIndexWarm",
    )
    _warm_thread.start()


def stop_detection_ticks_warmer() -> None:
    _warm_stop.set()
