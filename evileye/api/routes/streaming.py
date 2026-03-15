import asyncio
from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import threading

from evileye.api.core.broker_access import get_broker
from evileye.api.core.config_run_access import get_config_run_manager

router = APIRouter(prefix="/api/v1", tags=["streaming"])


def _resolve_pipeline(rid: int) -> str:
    """Resolve rid to pipeline_id string for FrameBroker.

    Checks ConfigRunManager. Frames arrive via file-based IPC (FramePoller).
    """
    try:
        run_info = get_config_run_manager().describe(rid)
        if run_info["state"] == "running":
            return str(rid)
        raise HTTPException(
            status_code=400,
            detail=f"Config Run '{rid}' is not running (state: {run_info['state']})",
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Pipeline '{rid}' not found") from exc


@router.get("/pipelines/{rid}/snapshot")
async def snapshot(rid: int):
    """
    Return the latest available JPEG snapshot for the given pipeline.
    """
    pipeline_id_str = _resolve_pipeline(rid)
    data = get_broker().latest_jpeg(pipeline_id_str)
    if not data:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=data, media_type="image/jpeg")


async def _mjpeg_generator(
    pipeline_id_str: str, fps: int, stop_event: threading.Event,
) -> AsyncGenerator[bytes, None]:
    boundary = b"--frame"
    delay = 1.0 / max(1, fps)

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
    fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    """
    MJPEG streaming endpoint.
    Sends a sequence of JPEG images in a single HTTP response.
    Browsers and players render it as a video stream thanks to
    'multipart/x-mixed-replace' and boundary markers.
    """
    pipeline_id_str = _resolve_pipeline(rid)
    stop_event = get_broker().start_stream(pipeline_id_str)

    return StreamingResponse(
        _mjpeg_generator(pipeline_id_str, fps, stop_event),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.post("/pipelines/{rid}/stream:stop")
async def stop_stream(rid: int):
    """
    Stop the active MJPEG stream for the given pipeline.
    """
    pipeline_id_str = _resolve_pipeline(rid)
    stopped = get_broker().stop_stream(pipeline_id_str)

    if stopped:
        return {
            "pipeline_id": rid,
            "status": "stopped",
            "message": f"Stream for pipeline '{rid}' has been stopped",
        }
    return {
        "pipeline_id": rid,
        "status": "not_found",
        "message": f"No active stream found for pipeline '{rid}'",
    }


@router.get("/pipelines/{rid}/stream:status")
async def stream_status(rid: int):
    """
    Get the status of the stream for the given pipeline.
    """
    pipeline_id_str = _resolve_pipeline(rid)
    is_active = get_broker().is_stream_active(pipeline_id_str)

    return {
        "pipeline_id": rid,
        "stream_active": is_active,
    }
