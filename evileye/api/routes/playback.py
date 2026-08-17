from __future__ import annotations

import asyncio
import mimetypes
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from evileye.api.core import playback_service as svc
from evileye.api.core import playback_metadata_service as metadata_svc

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])


@router.get("/cameras")
async def playback_cameras(
    date: Optional[str] = None,
    run_id: Optional[int] = Query(None),
) -> dict:
    if run_id is not None:
        items = await asyncio.to_thread(svc.list_logical_cameras, run_id, date)
    else:
        items = await asyncio.to_thread(svc.discover_cameras, date)
    return {"items": items}


@router.get("/segments")
async def playback_segments(
    camera: Optional[str] = Query(None),
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids for batch"),
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    date: Optional[str] = None,
) -> dict:
    if cameras:
        cam_list = [c.strip() for c in cameras.split(",") if c.strip()]
        by_camera = await asyncio.to_thread(svc.load_segments_batch, cam_list, from_ts, to_ts, date)
        return {"by_camera": by_camera, "items": [item for items in by_camera.values() for item in items]}
    if not camera:
        raise HTTPException(status_code=400, detail="camera or cameras query required")
    items = await asyncio.to_thread(svc.load_segments, camera, from_ts, to_ts, date)
    return {"items": items}


@router.get("/events")
async def playback_events(
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    camera: Optional[str] = None,
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids"),
    date: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    cam_list = [c.strip() for c in (cameras or "").split(",") if c.strip()]
    items = await asyncio.to_thread(
        svc.load_event_markers,
        from_ts,
        to_ts,
        camera,
        cam_list or None,
        date=date,
        limit=limit,
    )
    return {"items": items}


@router.get("/metadata")
async def playback_metadata(
    camera: Optional[str] = Query(None),
    cameras: Optional[str] = Query(None, description="Comma-separated camera ids for batch"),
    ts: Optional[float] = Query(None, description="Unix timestamp (seconds); optional for static_only"),
    date: Optional[str] = None,
    run_id: Optional[int] = Query(None),
    window: float = Query(1.0, ge=0.1, le=10.0),
    source_id: Optional[int] = Query(None),
    static_only: bool = Query(False, description="Return config-only layers (zones, ROI)"),
    frame_w: Optional[int] = Query(None, ge=1, description="Actual video frame width from client"),
    frame_h: Optional[int] = Query(None, ge=1, description="Actual video frame height from client"),
) -> dict:
    effective_ts = float(ts if ts is not None else 0.0)
    if not static_only and ts is None:
        raise HTTPException(status_code=400, detail="ts query required unless static_only=true")
    if cameras:
        cam_list = [c.strip() for c in cameras.split(",") if c.strip()]
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


@router.get("/media")
async def playback_media(path: str = Query(...)):
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
