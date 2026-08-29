"""Background warmer for compact detection_ticks.json across archive dates."""

from __future__ import annotations

import logging
import threading
import time

logger = logging.getLogger(__name__)

_warm_stop = threading.Event()
_warm_thread: threading.Thread | None = None


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


def _cameras_for_warm(*, run_id: int | None = None) -> list[str]:
    from evileye.api.core.playback_service import list_logical_cameras

    cams = []
    try:
        for row in list_logical_cameras(run_id=run_id):
            name = str(row.get("id") or row.get("source_name") or "").strip()
            # Prefer logical source names; skip composite storage-only folder ids.
            if not name or ("-" in name and not row.get("split")):
                # Keep split children (Cam2); drop accidental parent folder ids when not a source.
                if "-" in name and row.get("parent_folder") == name:
                    continue
            if name:
                cams.append(name)
    except Exception as exc:
        logger.debug("list_logical_cameras for warm failed: %s", exc)
    # Prefer non-composite names when both Cam2 and Cam2-Cam3 appear.
    plain = [c for c in cams if "-" not in c]
    return sorted(set(plain or cams))


def _needs_rebuild(date_folder: str, *, run_id: int | None = None) -> bool:
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
    # Skip thrashing today's soft-fresh file within TODAY_REBUILD_SEC.
    data = _read_json(index_path)
    if (
        data
        and int(data.get("version") or 0) == INDEX_VERSION
        and _is_today(date_folder)
        and (time.time() - float(data.get("built_at") or 0.0)) < TODAY_REBUILD_SEC
    ):
        return False
    return True


def warm_detection_ticks_for_date(
    date_folder: str,
    *,
    run_id: int | None = None,
    cameras: list[str] | None = None,
) -> str:
    """Build ticks for one date if missing/stale. Returns status: built|skip|fail."""
    from evileye.api.core.playback_timeline_index import _rebuild_detection_ticks
    from evileye.api.core.singleflight import singleflight

    if not _needs_rebuild(date_folder, run_id=run_id):
        logger.info("detection_ticks warm date=%s status=skip elapsed_ms=0", date_folder)
        return "skip"

    cam_list = list(cameras or _cameras_for_warm(run_id=run_id))
    if not cam_list:
        logger.info("detection_ticks warm date=%s status=skip elapsed_ms=0 reason=no_cameras", date_folder)
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


def _warm_loop(run_id: int | None = None) -> None:
    # Stagger after startup so Live/unix relay settle first.
    if _warm_stop.wait(8.0):
        return
    try:
        dates = list_detection_dates(run_id=run_id)
        cameras = _cameras_for_warm(run_id=run_id)
        logger.info(
            "detection_ticks warm start dates=%s cameras=%s",
            len(dates),
            len(cameras),
        )
        for date_folder in dates:
            if _warm_stop.is_set():
                break
            warm_detection_ticks_for_date(date_folder, run_id=run_id, cameras=cameras)
            # Yield between days so HTTP detections can grab the GIL/disk.
            if _warm_stop.wait(0.25):
                break
        logger.info("detection_ticks warm finished")
    except Exception as exc:
        logger.warning("detection_ticks warm aborted: %s", exc)


def start_detection_ticks_warmer(*, run_id: int | None = None) -> None:
    global _warm_thread
    if _warm_thread is not None and _warm_thread.is_alive():
        return
    _warm_stop.clear()
    _warm_thread = threading.Thread(
        target=_warm_loop,
        kwargs={"run_id": run_id},
        daemon=True,
        name="DetectionTicksWarm",
    )
    _warm_thread.start()


def stop_detection_ticks_warmer() -> None:
    _warm_stop.set()
