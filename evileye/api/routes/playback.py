from __future__ import annotations

import asyncio
import mimetypes
from typing import Optional

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

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])

_PLAYBACK_ROUTE_TIMEOUT_SEC = 2.0


async def _to_thread_with_timeout(fn, *args, err_detail: str, **kwargs):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(fn, *args, **kwargs),
            timeout=_PLAYBACK_ROUTE_TIMEOUT_SEC,
        )
    except asyncio.TimeoutError:
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


@router.get("/cameras")
async def playback_cameras(
    request: Request,
    date: Optional[str] = None,
    run_id: Optional[int] = Query(None),
) -> dict:
    if run_id is not None:
        items = await _to_thread_with_timeout(
            svc.list_logical_cameras, run_id, date, err_detail="playback_cameras timeout"
        )
    else:
        items = await _to_thread_with_timeout(
            svc.discover_cameras, date, err_detail="playback_cameras timeout"
        )
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
        by_camera = await _to_thread_with_timeout(
            svc.load_segments_batch, cam_list, from_ts, to_ts, date, err_detail="playback_segments timeout"
        )
        return {"by_camera": by_camera, "items": [item for items in by_camera.values() for item in items]}
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    _require_cameras(access, [camera], single=True)
    items = await _to_thread_with_timeout(
        svc.load_segments, camera, from_ts, to_ts, date, err_detail="playback_segments timeout"
    )
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
    from evileye.api.core.playback_timeline_index import build_timeline

    access = resolve_camera_access(request)
    cam_list = _require_cameras(access, [c.strip() for c in cameras.split(",") if c.strip()], single=False)
    if not cam_list:
        raise HTTPException(status_code=400, detail="cameras query required")
    return await _to_thread_with_timeout(
        build_timeline,
        err_detail="playback_timeline timeout",
        date_folder=date,
        cameras=cam_list,
        run_id=run_id,
        from_ts=from_ts,
        to_ts=to_ts,
    )


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
