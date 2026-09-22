"""Background warmer for playback on-disk indexes across archive dates.

Runs continuously (daemon loop) so recent archive days stay warm as new
recordings and journals appear — not only once at API startup.
"""

from __future__ import annotations

import logging
import os
import threading
import time
from datetime import date, timedelta

logger = logging.getLogger(__name__)

_warm_stop = threading.Event()
_warm_thread: threading.Thread | None = None

_WARM_RECENT_DAYS = int(os.getenv("EVILEYE_PLAYBACK_WARM_RECENT_DAYS", "14") or 14)
_WARM_INTERVAL_SEC = float(os.getenv("EVILEYE_PLAYBACK_WARM_INTERVAL_SEC", "300") or 300)


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


def list_event_dates(*, run_id: int | None = None) -> list[str]:
    """Return YYYY-MM-DD folders under Events that have metadata."""
    from evileye.api.core import playback_metadata_service as meta

    params = meta._load_params_for_run(run_id)
    base = meta._playback_data_dir(params) / "Events"
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
        if meta_dir.is_dir() and any(meta_dir.iterdir()):
            out.append(name)
            continue
        if any(path.iterdir()):
            out.append(name)
    return out


def _recent_dates(dates: list[str], *, limit: int = _WARM_RECENT_DAYS) -> list[str]:
    if limit <= 0:
        return list(dates)
    return list(dates)[-limit:]


def _prioritize_dates(dates: list[str]) -> list[str]:
    """Today first, then yesterday, then remaining newest-first."""
    if not dates:
        return []
    today = date.today().isoformat()
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    unique = sorted(set(dates), reverse=True)
    head: list[str] = []
    if today in unique:
        head.append(today)
    if yesterday in unique and yesterday != today:
        head.append(yesterday)
    head_set = set(head)
    return head + [d for d in unique if d not in head_set]


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


def _tally_statuses(statuses: dict[str, str]) -> tuple[int, int, int]:
    built = skip = fail = 0
    for status in statuses.values():
        if status == "built":
            built += 1
        elif status == "fail":
            fail += 1
        else:
            skip += 1
    return built, skip, fail


def _warm_loop(run_id: int | None = None) -> None:
    """Continuous warm cycles until stop_detection_ticks_warmer()."""
    if _warm_stop.wait(8.0):
        return
    while not _warm_stop.is_set():
        t0 = time.time()
        built = skip = fail = 0
        try:
            stream_dates = _recent_dates(list_stream_dates(run_id=run_id))
            det_dates = _recent_dates(list_detection_dates(run_id=run_id))
            event_dates = _recent_dates(list_event_dates(run_id=run_id))
            dates = _prioritize_dates(sorted(set(stream_dates) | set(det_dates) | set(event_dates)))
            cameras = _cameras_for_warm(run_id=run_id)
            logger.info(
                "playback_index warm cycle start dates=%s cameras=%s recent_limit=%s interval_sec=%s",
                len(dates),
                len(cameras),
                _WARM_RECENT_DAYS,
                _WARM_INTERVAL_SEC,
            )
            for date_folder in dates:
                if _warm_stop.is_set():
                    break
                if (
                    not _needs_segment_rebuild(date_folder)
                    and not _needs_detection_rebuild(date_folder, run_id=run_id)
                    and not _needs_event_rebuild(date_folder, cameras)
                ):
                    skip += 3
                    continue
                statuses = warm_playback_indexes_for_date(
                    date_folder, run_id=run_id, cameras=cameras
                )
                b, s, f = _tally_statuses(statuses)
                built += b
                skip += s
                fail += f
                if _warm_stop.wait(0.25):
                    break
            logger.info(
                "playback_index warm cycle end elapsed_ms=%s built=%s skip=%s fail=%s",
                int((time.time() - t0) * 1000),
                built,
                skip,
                fail,
            )
        except Exception as exc:
            logger.warning("playback_index warm cycle aborted: %s", exc)
        elapsed = time.time() - t0
        wait_sec = max(1.0, float(_WARM_INTERVAL_SEC) - elapsed)
        if _warm_stop.wait(wait_sec):
            break


def start_detection_ticks_warmer(*, run_id: int | None = None) -> None:
    """Start the continuous playback index warmer (historical name)."""
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
