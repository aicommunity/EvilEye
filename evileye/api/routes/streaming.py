import asyncio
from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import threading

from evileye.api.core.broker_access import get_broker
from evileye.api.core.manager_access import get_manager
from evileye.api.core.pipeline_manager import PipelineState

router = APIRouter(prefix="/api/v1", tags=["streaming"])


@router.get("/pipelines/{rid}/snapshot")
async def snapshot(rid: int):
    """
    Return the latest available JPEG snapshot for the given pipeline.
    """
    try:
        pipeline_info = get_manager().describe(rid)
        if pipeline_info["state"] not in [PipelineState.RUNNING, PipelineState.STARTING]:
            raise HTTPException(status_code=400, detail=f"Pipeline '{rid}' is not running (state: {pipeline_info['state']})")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pid}' not found")
    
    data = get_broker().latest_jpeg(str(rid))
    if not data:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=data, media_type="image/jpeg")


async def _mjpeg_generator(rid: int, fps: int, stop_event: threading.Event) -> AsyncGenerator[bytes, None]:
    """
    Asynchronous generator that yields MJPEG frames for streaming.
    Stops when stop_event is set.
    """
    boundary = b"--frame"
    delay = 1.0 / max(1, fps)
    pipeline_id_str = str(pid)
    
    while not stop_event.is_set():
        data = get_broker().latest_jpeg(pipeline_id_str)
        if data:
            yield (
                boundary
                + b"\r\n"
                + b"Content-Type: image/jpeg\r\n\r\n"
                + data
                + b"\r\n"
            )
        
        elapsed = 0
        check_interval = 0.1
        while elapsed < delay and not stop_event.is_set():
            await asyncio.sleep(min(check_interval, delay - elapsed))
            elapsed += check_interval


@router.get("/pipelines/{rid}/stream.mjpg")
async def mjpeg_stream(
    rid: int,
    fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)")
):
    """
    MJPEG streaming endpoint.
    Sends a sequence of JPEG images in a single HTTP response.
    Browsers and players render it as a video stream thanks to
    'multipart/x-mixed-replace' and boundary markers
    """
    try:
        pipeline_info = get_manager().describe(pid)
        if pipeline_info["state"] not in [PipelineState.RUNNING, PipelineState.STARTING]:
            raise HTTPException(status_code=400, detail=f"Pipeline '{pid}' is not running (state: {pipeline_info['state']})")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pid}' not found")
    
    stop_event = get_broker().start_stream(str(pid))
    
    return StreamingResponse(
        _mjpeg_generator(pid, fps, stop_event),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0"
        }
    )


@router.post("/pipelines/{rid}/stream:stop")
async def stop_stream(rid: int):
    """
    Stop the active MJPEG stream for the given pipeline.
    This will cause the stream generator to exit gracefully.
    """
    try:
        pipeline_info = get_manager().describe(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pid}' not found")
    
    stopped = get_broker().stop_stream(str(pid))
    
    if stopped:
        return {
            "pipeline_id": pid,
            "status": "stopped",
            "message": f"Stream for pipeline '{pid}' has been stopped"
        }
    else:
        return {
            "pipeline_id": pid,
            "status": "not_found",
            "message": f"No active stream found for pipeline '{pid}'"
        }


@router.get("/pipelines/{rid}/stream:status")
async def stream_status(rid: int):
    """
    Get the status of the stream for the given pipeline.
    """
    try:
        pipeline_info = get_manager().describe(pid)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pid}' not found")
    
    is_active = get_broker().is_stream_active(str(pid))
    
    return {
        "pipeline_id": pid,
        "stream_active": is_active,
        "pipeline_state": pipeline_info["state"]
    }
