import asyncio
import time
from fastapi import APIRouter, HTTPException, Response, Query
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import threading

from evileye.api.core.broker_access import get_broker
from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.runtime_registry import load_runtime_record

router = APIRouter(prefix="/api/v1", tags=["streaming"])


def _resolve_run(rid: int) -> dict:
    """Resolve run id to runtime record and validate availability.

    First checks the legacy ConfigRunManager, then the shared runtime registry.
    """
    runtime_info = load_runtime_record(rid)
    try:
        run_info = get_config_run_manager().describe(rid)
    except KeyError:
        run_info = None
    if run_info and runtime_info:
        run_info = {**runtime_info, **run_info}
    elif runtime_info:
        run_info = runtime_info
    if not run_info:
        raise HTTPException(status_code=404, detail=f"Run '{rid}' not found")
    if run_info.get("state") != "running":
        raise HTTPException(
            status_code=400,
            detail=f"Run '{rid}' is not running (state: {run_info.get('state')})",
        )
    return run_info


def _load_latest_frame(run_info: dict) -> bytes | None:
    run_id_str = str(run_info["id"])
    data = get_broker().latest_jpeg(run_id_str)
    if data:
        return data
    frame_dir = run_info.get("frame_dir")
    if not frame_dir:
        return None
    try:
        from pathlib import Path

        latest_path = Path(frame_dir) / "latest.jpg"
        if latest_path.exists():
            payload = latest_path.read_bytes()
            if payload:
                get_broker().publish_jpeg(
                    run_id_str,
                    payload,
                    metadata={"timestamp": time.time(), "content_type": "image/jpeg", "transport": "file_runtime"},
                )
                return payload
    except Exception:
        return None
    return None


def _web_stream_available(run_info: dict, *, has_frame: bool | None = None) -> bool:
    if has_frame is None:
        has_frame = _load_latest_frame(run_info) is not None
    return bool(run_info.get("state") == "running" and has_frame)


def _stream_status_payload(rid: int, run_info: dict) -> dict:
    run_id_str = str(run_info["id"])
    is_active = get_broker().is_stream_active(run_id_str)
    has_frame = _load_latest_frame(run_info) is not None
    web_stream_available = _web_stream_available(run_info, has_frame=has_frame)
    return {
        "run_id": rid,
        "pipeline_id": rid,
        "stream_active": is_active,
        "has_frame": has_frame,
        "web_stream_available": web_stream_available,
        "frame_dir_configured": bool(run_info.get("frame_dir")),
    }


async def _snapshot_impl(rid: int):
    """
    Return the latest available JPEG snapshot for the given runtime.
    """
    run_info = _resolve_run(rid)
    data = _load_latest_frame(run_info)
    if not data:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(content=data, media_type="image/jpeg")


@router.get("/runs/{rid}/snapshot")
async def snapshot(rid: int):
    return await _snapshot_impl(rid)


@router.get("/pipelines/{rid}/snapshot", deprecated=True)
async def snapshot_legacy(rid: int):
    return await _snapshot_impl(rid)


async def _mjpeg_generator(
    run_info: dict, fps: int, stop_event: threading.Event,
) -> AsyncGenerator[bytes, None]:
    run_id_str = str(run_info["id"])
    boundary = b"--frame"
    delay = 1.0 / max(1, fps)

    while not stop_event.is_set():
        data = _load_latest_frame(run_info)
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


async def _mjpeg_stream_impl(
    rid: int,
    fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    """
    MJPEG streaming endpoint.
    Sends a sequence of JPEG images in a single HTTP response.
    Browsers and players render it as a video stream thanks to
    'multipart/x-mixed-replace' and boundary markers.
    """
    run_info = _resolve_run(rid)
    if not _web_stream_available(run_info):
        raise HTTPException(
            status_code=409,
            detail="Web stream is unavailable for this run. Restart it with frame sharing enabled.",
        )
    run_id_str = str(run_info["id"])
    stop_event = get_broker().start_stream(run_id_str)

    return StreamingResponse(
        _mjpeg_generator(run_info, fps, stop_event),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers={
            "X-Accel-Buffering": "no",
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/runs/{rid}/stream.mjpg")
async def mjpeg_stream(
    rid: int,
    fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    return await _mjpeg_stream_impl(rid, fps)


@router.get("/pipelines/{rid}/stream.mjpg", deprecated=True)
async def mjpeg_stream_legacy(
    rid: int,
    fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    return await _mjpeg_stream_impl(rid, fps)


async def _stop_stream_impl(rid: int):
    """
    Stop the active MJPEG stream for the given run.
    """
    run_info = _resolve_run(rid)
    run_id_str = str(run_info["id"])
    stopped = get_broker().stop_stream(run_id_str)

    if stopped:
        return {
            "run_id": rid,
            "pipeline_id": rid,
            "status": "stopped",
            "message": f"Stream for run '{rid}' has been stopped",
        }
    return {
        "run_id": rid,
        "pipeline_id": rid,
        "status": "not_found",
        "message": f"No active stream found for run '{rid}'",
    }


@router.post("/runs/{rid}/stream:stop")
async def stop_stream(rid: int):
    return await _stop_stream_impl(rid)


@router.post("/pipelines/{rid}/stream:stop", deprecated=True)
async def stop_stream_legacy(rid: int):
    return await _stop_stream_impl(rid)


async def _stream_status_impl(rid: int):
    """
    Get the status of the stream for the given run.
    """
    run_info = _resolve_run(rid)
    return _stream_status_payload(rid, run_info)


@router.get("/runs/{rid}/stream:status")
async def stream_status(rid: int):
    return await _stream_status_impl(rid)


@router.get("/pipelines/{rid}/stream:status", deprecated=True)
async def stream_status_legacy(rid: int):
    return await _stream_status_impl(rid)
