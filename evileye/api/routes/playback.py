from __future__ import annotations

import asyncio
import mimetypes
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from evileye.api.core import playback_service as svc

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])


@router.get("/cameras")
async def playback_cameras(date: Optional[str] = None) -> dict:
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
    date: Optional[str] = None,
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    items = await asyncio.to_thread(
        svc.load_event_markers, from_ts, to_ts, camera, date=date, limit=limit,
    )
    return {"items": items}


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
