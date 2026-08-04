from __future__ import annotations

import mimetypes
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from evileye.api.core import playback_service as svc

router = APIRouter(prefix="/api/v1/playback", tags=["playback"])


@router.get("/cameras")
async def playback_cameras(date: Optional[str] = None) -> dict:
    return {"items": svc.discover_cameras(date)}


@router.get("/segments")
async def playback_segments(
    camera: str = Query(...),
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    date: Optional[str] = None,
) -> dict:
    return {"items": svc.load_segments(camera, from_ts, to_ts, date=date)}


@router.get("/events")
async def playback_events(
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    camera: Optional[str] = None,
) -> dict:
    return {"items": svc.load_event_markers(from_ts, to_ts, camera)}


@router.get("/media")
async def playback_media(path: str = Query(...)):
    try:
        resolved = svc.resolve_media_path(path)
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
