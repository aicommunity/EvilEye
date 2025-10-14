import asyncio
from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator

from evileye.api.core.broker_access import get_broker
from evileye.api.core.manager_access import get_manager
from evileye.api.core.pipeline_manager import PipelineState

router = APIRouter(prefix="/api/v1", tags=["streaming"])


@router.get("/pipelines/{pid}/snapshot")
async def snapshot(pid: int):
    """
    Return the latest available JPEG snapshot for the given pipeline.
    """
    try:
        pipeline_info = get_manager().describe(pid)
        if pipeline_info["state"] not in [PipelineState.RUNNING, PipelineState.STARTING]:
            raise HTTPException(status_code=400, detail=f"Pipeline '{pid}' is not running (state: {pipeline_info['state']})")
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Pipeline '{pid}' not found")
    
    data = get_broker().latest_jpeg(str(pid))
    if not data:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=data, media_type="image/jpeg")


async def _mjpeg_generator(pid: int, fps: int) -> AsyncGenerator[bytes, None]:
    """
    Asynchronous generator that yields MJPEG frames for streaming.
    """
    boundary = b"--frame"
    delay = 1.0 / max(1, fps)
    while True:
        data = get_broker().latest_jpeg(str(pid))
        if data:
            yield (
                boundary
                + b"\r\n"
                + b"Content-Type: image/jpeg\r\n\r\n"
                + data
                + b"\r\n"
            )
        await asyncio.sleep(delay)


@router.get("/pipelines/{pid}/stream.mjpg")
async def mjpeg_stream(
    pid: int,
    fps: int = Query(10, ge=1, le=60, description="Frames per second (1–60)")
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
    
    return StreamingResponse(
        _mjpeg_generator(pid, fps),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
