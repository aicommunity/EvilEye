from __future__ import annotations

import asyncio
import mimetypes
import threading
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

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])

_memory_lock = threading.Lock()
_memory_cache: dict[str, Any] = {}


def _remember(key: str, value: Any) -> None:
    with _memory_lock:
        _memory_cache[key] = deepcopy(value)


def _recall(key: str) -> Any | None:
    with _memory_lock:
        cached = _memory_cache.get(key)
        return deepcopy(cached) if cached is not None else None


async def _to_thread_with_timeout_or_cached(
    value_fn: Callable[[], Any],
    cached_fn: Callable[[], Any | None],
    *,
    err_detail: str,
    on_timeout: Callable[[], None] | None = None,
):
    timeout = playback_route_timeout_sec()
    try:
        return await asyncio.wait_for(asyncio.to_thread(value_fn), timeout=timeout)
    except asyncio.TimeoutError:
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
    from evileye.api.core.playback_timeline_index import build_timeline, schedule_segment_index_refresh

    access = resolve_camera_access(request)
    cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
    if not cam_list:
        raise HTTPException(status_code=400, detail="cameras query required")
    mem_key = f"playback:timeline:{date}:{run_id}:{from_ts}:{to_ts}:{','.join(cam_list)}"

    def _load():
        return build_timeline(
            date_folder=date,
            cameras=cam_list,
            run_id=run_id,
            from_ts=from_ts,
            to_ts=to_ts,
        )

    def _cached():
        mem = _recall(mem_key)
        if mem is not None:
            return mem
        return _stale_timeline(date, cam_list, from_ts, to_ts)

    payload = await _to_thread_with_timeout_or_cached(
        _load,
        _cached,
        err_detail="playback_timeline timeout",
        on_timeout=lambda: schedule_segment_index_refresh(date, cam_list),
    )
    _remember(mem_key, payload)
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
    intervals = await asyncio.to_thread(
        svc.load_event_intervals,
        from_ts,
        to_ts,
        camera,
        cam_list or None,
        date=date,
        limit=limit,
    )
    legacy_markers = await asyncio.to_thread(
        svc.load_event_markers,
        from_ts,
        to_ts,
        camera,
        cam_list or None,
        date=date,
        limit=limit,
    )
    return {"items": intervals, "legacy_markers": legacy_markers}


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
        by_camera = await asyncio.to_thread(
            metadata_svc.build_playback_metadata_batch,
            cameras=cam_list,
            ts=effective_ts,
            date=date,
            run_id=run_id,
            window_sec=window,
            static_only=static_only,
            frame_w=frame_w,
            frame_h=frame_h,
        )
        return {"by_camera": by_camera}
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    _require_cameras(access, [camera], single=True)
    if static_only:
        payload = await asyncio.to_thread(
            metadata_svc.build_playback_static_metadata,
            camera=camera,
            run_id=run_id,
            source_id=source_id,
            frame_w=frame_w,
            frame_h=frame_h,
        )
    else:
        payload = await asyncio.to_thread(
            metadata_svc.build_playback_metadata,
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
    if cameras:
        cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
        by_camera = await asyncio.to_thread(
            metadata_svc.load_detection_index_batch,
            cameras=cam_list,
            date_folder=date,
            run_id=run_id,
            from_ts=from_ts,
            to_ts=to_ts,
            ticks_only=ticks_only,
        )
        return {"by_camera": by_camera, "items": [item for items in by_camera.values() for item in items]}
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    _require_cameras(access, [camera], single=True)
    items = await asyncio.to_thread(
        metadata_svc.load_detection_index,
        camera=camera,
        date_folder=date,
        run_id=run_id,
        from_ts=from_ts,
        to_ts=to_ts,
        ticks_only=ticks_only,
    )
    return {"items": items}


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
