"""
Internal API: receive JPEG frames from external runtimes so streaming endpoints
work without file-based frame handoff.
"""
from fastapi import APIRouter, Request, HTTPException, Query

from evileye.core.runtime_services import get_frame_broker

router = APIRouter(prefix="/api/v1/internal", tags=["internal"], include_in_schema=False)


@router.post("/frames/{rid}")
async def receive_frame(rid: int, request: Request, source_id: int | None = Query(None)) -> dict:
    """Accept JPEG from runtime process; store in FrameBroker for unified streaming."""
    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty body")
    metadata = {
        "source_id": source_id,
        "content_type": request.headers.get("content-type", "image/jpeg"),
        "transport": "http_internal",
    }
    broker = get_frame_broker()
    broker.publish_jpeg(str(rid), body, metadata=metadata)
    if source_id is not None:
        broker.publish_jpeg(f"{rid}:{source_id}", body, metadata=metadata)
    return {"ok": True, "size": len(body), "source_id": source_id}
