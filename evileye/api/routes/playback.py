from __future__ import annotations

import asyncio
import logging
import mimetypes
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from typing import Any, Callable, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from evileye.api.core import playback_service as svc
from evileye.api.core import playback_metadata_service as metadata_svc
from evileye.api.core.camera_access import (
    assert_name_allowed,
    filter_by_source_name,
    intersect_camera_query,
    resolve_camera_access,
)
from evileye.api.core.playback_metadata_service import DEFAULT_MATCH_SEC
from evileye.api.core.route_timeouts import playback_route_timeout_sec

logger = logging.getLogger("evileye.api.playback")

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])

_memory_lock = threading.Lock()
# key -> (expires_at_or_None, value). expires_at None = sticky timeout fallback only.
_memory_cache: dict[str, tuple[float | None, Any]] = {}
_TIMELINE_HAPPY_TTL_SEC = 45.0
_TIMELINE_SLOT_WAIT_SEC = 15.0
# Keep light endpoints off the default pool so timeline rebuilds cannot starve /cameras.
_light_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="playback-light")
# Heavy journal scans — tiny pool + semaphore so wheel/seek storms cannot open unbounded work.
_detections_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="playback-det")
_timeline_slots = asyncio.Semaphore(2)
_detections_slots = asyncio.Semaphore(2)
_DETECTIONS_HAPPY_TTL_SEC = 30.0


def _remember(key: str, value: Any, *, ttl_sec: float | None = None) -> None:
    expires_at = (time.time() + float(ttl_sec)) if ttl_sec is not None else None
    with _memory_lock:
        _memory_cache[key] = (expires_at, deepcopy(value))


def _recall(key: str, *, require_fresh: bool = False) -> Any | None:
    with _memory_lock:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        expires_at, cached = entry
        if require_fresh:
            if expires_at is None or expires_at <= time.time():
                return None
        return deepcopy(cached)


async def _to_thread_with_timeout_or_cached(
    value_fn: Callable[[], Any],
    cached_fn: Callable[[], Any | None],
    *,
    err_detail: str,
    on_timeout: Callable[[], None] | None = None,
    executor: ThreadPoolExecutor | None = None,
    log_ctx: dict[str, Any] | None = None,
):
    timeout = playback_route_timeout_sec()
    try:
        if executor is not None:
            loop = asyncio.get_running_loop()
            fut = loop.run_in_executor(executor, value_fn)
            return await asyncio.wait_for(fut, timeout=timeout)
        return await asyncio.wait_for(asyncio.to_thread(value_fn), timeout=timeout)
    except asyncio.TimeoutError:
        logger.warning(
            "playback route timeout detail=%s timeout_sec=%s executor=%s %s",
            err_detail,
            timeout,
            "light" if executor is _light_pool else ("detections" if executor is _detections_pool else "default"),
            " ".join(f"{k}={v}" for k, v in (log_ctx or {}).items()),
        )
        if on_timeout is not None:
            try:
                on_timeout()
            except Exception:
                pass
        cached = cached_fn()
        if cached is not None:
            return cached
        raise HTTPException(status_code=503, detail=err_detail)


def _require_cameras(access, names: list[str], *, single: bool) -> list[str]:
    allowed = intersect_camera_query(access, names, hard=True)
    if single and names and not allowed:
        raise HTTPException(status_code=403, detail="Camera access denied")
    if not single and names and not allowed:
        raise HTTPException(status_code=403, detail="Camera access denied")
    denied = [n for n in names if n not in allowed]
    if single and denied:
        raise HTTPException(status_code=403, detail="Camera access denied")
    return allowed


def _camera_name_from_media_path(path: str) -> str | None:
    """Best-effort: Streams/YYYY-MM-DD/<folder>/file.mp4 → folder or split part."""
    from pathlib import Path

    try:
        parts = Path(path).parts
    except Exception:
        return None
    for i, part in enumerate(parts):
        if part == "Streams" and i + 2 < len(parts):
            folder = parts[i + 2]
            if "-" in folder:
                # composite split folder — cannot map to single logical without more context
                return folder.split("-")[0]
            return folder
    return None


def _stale_segments_by_camera(
    date: str | None,
    cameras: list[str],
    from_ts: float | None,
    to_ts: float | None,
) -> dict[str, list[dict[str, Any]]] | None:
    if not date:
        return None
    from evileye.api.core.playback_timeline_index import (
        filter_segments_window,
        read_segment_index_stale,
    )

    stale = read_segment_index_stale(date)
    if stale is None:
        return None
    return {
        cam: filter_segments_window(stale.get(cam) or [], from_ts, to_ts)
        for cam in cameras
    }


def _stale_timeline(
    date: str,
    cameras: list[str],
    from_ts: float | None,
    to_ts: float | None,
) -> dict[str, Any] | None:
    from evileye.api.core.playback_timeline_index import (
        filter_segments_window,
        read_segment_index_stale,
    )

    stale = read_segment_index_stale(date)
    if stale is None:
        return None
    by_camera: dict[str, Any] = {}
    for cam in cameras:
        by_camera[cam] = {
            "segments": filter_segments_window(stale.get(cam) or [], from_ts, to_ts),
            "detection_ticks": [],
            "events": [],
        }
    return {"date": date, "by_camera": by_camera, "stale": True}


@router.get("/cameras")
async def playback_cameras(
    request: Request,
    date: Optional[str] = None,
    run_id: Optional[int] = Query(None),
) -> dict:
    cache_key = f"playback:cameras:{run_id}:{date}"

    def _load():
        if run_id is not None:
            return svc.list_logical_cameras(run_id, date)
        return svc.discover_cameras(date)

    items = await _to_thread_with_timeout_or_cached(
        _load,
        lambda: _recall(cache_key),
        err_detail="playback_cameras timeout",
        executor=_light_pool,
    )
    _remember(cache_key, items)
    access = resolve_camera_access(request)
    filtered = filter_by_source_name(items or [], access, key="id", use_visible=True)
    return {"items": filtered}


@router.get("/segments")
async def playback_segments(
    request: Request,
    camera: Optional[str] = Query(None),
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids for batch"),
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    date: Optional[str] = None,
) -> dict:
    access = resolve_camera_access(request)
    if cameras:
        cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
        mem_key = f"playback:segments:{date}:{from_ts}:{to_ts}:{','.join(cam_list)}"

        def _load():
            return svc.load_segments_batch(cam_list, from_ts, to_ts, date)

        def _cached():
            mem = _recall(mem_key)
            if mem is not None:
                return mem
            return _stale_segments_by_camera(date, cam_list, from_ts, to_ts)

        def _on_timeout():
            if date:
                from evileye.api.core.playback_timeline_index import schedule_segment_index_refresh

                schedule_segment_index_refresh(date, cam_list)

        by_camera = await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            err_detail="playback_segments timeout",
            on_timeout=_on_timeout,
        )
        _remember(mem_key, by_camera)
        return {"by_camera": by_camera, "items": [item for items in by_camera.values() for item in items]}
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    _require_cameras(access, [camera], single=True)
    mem_key = f"playback:segments:{date}:{from_ts}:{to_ts}:{camera}"

    def _load_one():
        return svc.load_segments(camera, from_ts, to_ts, date)

    def _cached_one():
        mem = _recall(mem_key)
        if mem is not None:
            return mem
        batch = _stale_segments_by_camera(date, [camera], from_ts, to_ts)
        if batch is None:
            return None
        return batch.get(camera) or []

    def _on_timeout_one():
        if date:
            from evileye.api.core.playback_timeline_index import schedule_segment_index_refresh

            schedule_segment_index_refresh(date, [camera])

    items = await _to_thread_with_timeout_or_cached(
        _load_one,
        _cached_one,
        err_detail="playback_segments timeout",
        on_timeout=_on_timeout_one,
    )
    _remember(mem_key, items)
    return {"items": items}


@router.get("/timeline")
async def playback_timeline(
    request: Request,
    date: str = Query(..., description="YYYY-MM-DD"),
    cameras: str = Query(..., description="Comma-separated camera ids"),
    run_id: Optional[int] = Query(None),
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
) -> dict:
    """Compact day timeline: segments + detection ticks + event intervals in one round-trip."""
    from evileye.api.core.playback_timeline_index import (
        schedule_detection_ticks_refresh,
        schedule_event_intervals_refresh,
        schedule_segment_index_refresh,
        build_timeline,
    )

    access = resolve_camera_access(request)
    cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
    if not cam_list:
        raise HTTPException(status_code=400, detail="cameras query required")
    mem_key = f"playback:timeline:{date}:{run_id}:{from_ts}:{to_ts}:{','.join(cam_list)}"

    fresh = _recall(mem_key, require_fresh=True)
    if fresh is not None:
        return fresh

    def _load():
        return build_timeline(
            date_folder=date,
            cameras=cam_list,
            run_id=run_id,
            from_ts=from_ts,
            to_ts=to_ts,
        )

    def _cached():
        mem = _recall(mem_key, require_fresh=False)
        if mem is not None:
            return mem
        return _stale_timeline(date, cam_list, from_ts, to_ts)

    def _on_timeout():
        schedule_segment_index_refresh(date, cam_list)
        schedule_detection_ticks_refresh(date, cam_list, run_id=run_id)
        schedule_event_intervals_refresh(date, cam_list)

    # Cap concurrent timeline rebuilds so the default thread pool stays responsive.
    try:
        await asyncio.wait_for(_timeline_slots.acquire(), timeout=0.05)
    except asyncio.TimeoutError:
        cached = _cached()
        if cached is not None:
            _on_timeout()
            return cached
        try:
            await asyncio.wait_for(_timeline_slots.acquire(), timeout=_TIMELINE_SLOT_WAIT_SEC)
        except asyncio.TimeoutError:
            logger.warning(
                "playback route timeout detail=playback_timeline slot_busy date=%s n_cameras=%s",
                date,
                len(cam_list),
            )
            stale = _cached()
            if stale is not None:
                _on_timeout()
                return stale
            raise HTTPException(status_code=503, detail="playback_timeline slot busy")
    try:
        payload = await _to_thread_with_timeout_or_cached(
            _load,
            _cached,
            err_detail="playback_timeline timeout",
            on_timeout=_on_timeout,
            log_ctx={"date": date, "n_cameras": len(cam_list), "route": "timeline"},
        )
    finally:
        _timeline_slots.release()
    _remember(mem_key, payload, ttl_sec=_TIMELINE_HAPPY_TTL_SEC)
    return payload


@router.get("/events")
async def playback_events(
    request: Request,
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    camera: Optional[str] = None,
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids"),
    date: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    access = resolve_camera_access(request)
    cam_list = [c.strip() for c in (cameras or "").split(",") if c.strip()]
    if camera:
        _require_cameras(access, [camera], single=True)
    if cam_list:
        cam_list = _require_cameras(access, cam_list, single=False)

    def _load():
        intervals = svc.load_event_intervals(
            from_ts,
            to_ts,
            camera,
            cam_list or None,
            date=date,
            limit=limit,
        )
        legacy_markers = svc.load_event_markers(
            from_ts,
            to_ts,
            camera,
            cam_list or None,
            date=date,
            limit=limit,
        )
        return {"items": intervals, "legacy_markers": legacy_markers}

    return await _to_thread_with_timeout_or_cached(
        _load,
        lambda: None,
        err_detail="playback_events timeout",
        log_ctx={
            "date": date,
            "n_cameras": len(cam_list) if cam_list else (1 if camera else 0),
            "route": "events",
        },
    )


@router.get("/metadata")
async def playback_metadata(
    request: Request,
    camera: Optional[str] = Query(None),
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids for batch"),
    ts: Optional[float] = Query(None, description="Unix timestamp (seconds); optional for static_only"),
    date: Optional[str] = None,
    run_id: Optional[int] = Query(None),
    window: float = Query(DEFAULT_MATCH_SEC, ge=0.01, le=10.0),
    source_id: Optional[int] = Query(None),
    static_only: bool = Query(False, description="Return config-only layers (zones, ROI)"),
    frame_w: Optional[int] = Query(None, ge=1, description="Actual video frame width from client"),
    frame_h: Optional[int] = Query(None, ge=1, description="Actual video frame height from client"),
) -> dict:
    access = resolve_camera_access(request)
    effective_ts = float(ts if ts is not None else 0.0)
    if not static_only and ts is None:
        raise HTTPException(status_code=400, detail="ts query required unless static_only=true")
    if cameras:
        cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)

        def _batch():
            return {
                "by_camera": metadata_svc.build_playback_metadata_batch(
                    cameras=cam_list,
                    ts=effective_ts,
                    date=date,
                    run_id=run_id,
                    window_sec=window,
                    static_only=static_only,
                    frame_w=frame_w,
                    frame_h=frame_h,
                )
            }

        return await _to_thread_with_timeout_or_cached(
            _batch,
            lambda: None,
            err_detail="playback_metadata timeout",
            log_ctx={"date": date, "n_cameras": len(cam_list), "route": "metadata"},
        )
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    _require_cameras(access, [camera], single=True)

    def _one():
        if static_only:
            payload = metadata_svc.build_playback_static_metadata(
                camera=camera,
                run_id=run_id,
                source_id=source_id,
                frame_w=frame_w,
                frame_h=frame_h,
            )
        else:
            payload = metadata_svc.build_playback_metadata(
                camera=camera,
                ts=effective_ts,
                date=date,
                run_id=run_id,
                window_sec=window,
                source_id=source_id,
                frame_w=frame_w,
                frame_h=frame_h,
            )
        return {"metadata": payload}

    return await _to_thread_with_timeout_or_cached(
        _one,
        lambda: None,
        err_detail="playback_metadata timeout",
        log_ctx={"date": date, "n_cameras": 1, "route": "metadata"},
    )


@router.get("/detections")
async def playback_detections(
    request: Request,
    camera: Optional[str] = Query(None),
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids for batch"),
    date: Optional[str] = None,
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    run_id: Optional[int] = Query(None),
    ticks_only: bool = Query(False, description="Return lightweight ts/kind/object_id rows only"),
) -> dict:
    access = resolve_camera_access(request)
    if not date:
        if from_ts is not None:
            from datetime import datetime as dt

            date = dt.fromtimestamp(float(from_ts)).strftime("%Y-%m-%d")
        elif to_ts is not None:
            from datetime import datetime as dt

            date = dt.fromtimestamp(float(to_ts)).strftime("%Y-%m-%d")
        else:
            from datetime import datetime as dt

            date = dt.now().strftime("%Y-%m-%d")

    # Quantize window so near-identical wheel/seek requests share one cache key.
    q_from = int(from_ts // 60) * 60 if from_ts is not None else None
    q_to = int(to_ts // 60) * 60 if to_ts is not None else None

    try:
        await asyncio.wait_for(_detections_slots.acquire(), timeout=2.0)
    except asyncio.TimeoutError:
        raise HTTPException(status_code=503, detail="playback_detections busy")

    try:
        if cameras:
            cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
            mem_key = (
                f"playback:detections:{date}:{run_id}:{q_from}:{q_to}:"
                f"{'ticks' if ticks_only else 'full'}:{','.join(cam_list)}"
            )

            def _batch():
                by_camera = metadata_svc.load_detection_index_batch(
                    cameras=cam_list,
                    date_folder=date,
                    run_id=run_id,
                    from_ts=from_ts,
                    to_ts=to_ts,
                    ticks_only=ticks_only,
                )
                return {"by_camera": by_camera, "items": [item for items in by_camera.values() for item in items]}

            fresh = _recall(mem_key, require_fresh=True)
            if fresh is not None:
                return fresh

            result = await _to_thread_with_timeout_or_cached(
                _batch,
                lambda: _recall(mem_key),
                err_detail="playback_detections timeout",
                executor=_detections_pool,
                log_ctx={"date": date, "n_cameras": len(cam_list), "route": "detections"},
            )
            _remember(mem_key, result, ttl_sec=_DETECTIONS_HAPPY_TTL_SEC)
            return result
        if not camera:
            raise HTTPException(status_code=400, detail="camera or cameras query required")
        _require_cameras(access, [camera], single=True)
        mem_key = (
            f"playback:detections:{date}:{run_id}:{q_from}:{q_to}:"
            f"{'ticks' if ticks_only else 'full'}:{camera}"
        )

        def _one():
            items = metadata_svc.load_detection_index(
                camera=camera,
                date_folder=date,
                run_id=run_id,
                from_ts=from_ts,
                to_ts=to_ts,
                ticks_only=ticks_only,
            )
            return {"items": items}

        fresh = _recall(mem_key, require_fresh=True)
        if fresh is not None:
            return fresh

        result = await _to_thread_with_timeout_or_cached(
            _one,
            lambda: _recall(mem_key),
            err_detail="playback_detections timeout",
            executor=_detections_pool,
            log_ctx={"date": date, "n_cameras": 1, "route": "detections"},
        )
        _remember(mem_key, result, ttl_sec=_DETECTIONS_HAPPY_TTL_SEC)
        return result
    finally:
        _detections_slots.release()


@router.get("/media")
async def playback_media(request: Request, path: str = Query(...)):
    access = resolve_camera_access(request)
    cam_name = _camera_name_from_media_path(path)
    if cam_name:
        # Composite folders may contain multiple logical cams; check first part hard ACL.
        # If folder is Cam2-Cam3, allow if user has any part — stricter: require first part.
        parts = cam_name.split("-") if "-" in str(path) else [cam_name]
        folder = None
        try:
            from pathlib import Path as P

            pparts = P(path).parts
            for i, part in enumerate(pparts):
                if part == "Streams" and i + 2 < len(pparts):
                    folder = pparts[i + 2]
                    break
        except Exception:
            folder = cam_name
        if folder and "-" in folder:
            allowed_any = access.unrestricted or any(
                p in access.allowed_names for p in folder.split("-") if p
            )
            if not allowed_any:
                raise HTTPException(status_code=403, detail="Camera access denied")
        else:
            assert_name_allowed(access, cam_name)
    try:
        resolved = await asyncio.to_thread(svc.resolve_media_path, path)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if not resolved.exists() or not resolved.is_file():
        raise HTTPException(status_code=404, detail="Media not found")
    media_type = mimetypes.guess_type(str(resolved))[0] or "application/octet-stream"
    return FileResponse(
        str(resolved),
        media_type=media_type,
        headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
    )
