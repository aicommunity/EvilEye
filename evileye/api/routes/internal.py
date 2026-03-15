"""
Internal API: receive JPEG frames from Config Run (child process) so streaming
endpoints work the same for in-process pipelines and config runs.
"""
from fastapi import APIRouter, Request, HTTPException

from evileye.api.core.broker_access import get_broker

router = APIRouter(prefix="/api/v1/internal", tags=["internal"], include_in_schema=False)


@router.post("/frames/{rid}")
async def receive_frame(rid: int, request: Request) -> dict:
    """Accept JPEG from Config Run process; store in FrameBroker for unified streaming."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")
    get_broker().publish_jpeg(str(rid), body)
    return {"ok": True, "size": len(body)}
