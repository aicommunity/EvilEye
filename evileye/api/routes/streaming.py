import asyncio
import os
import time
from fastapi import APIRouter, HTTPException, Response, Query, Request
from fastapi.responses import StreamingResponse
from typing import AsyncGenerator
import threading

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.runtime_registry import load_runtime_record
from evileye.api.core.server_state import get_run_summary
from evileye.core.runtime_services import get_frame_broker

router = APIRouter(prefix="/api/v1", tags=["streaming"])

_mjpeg_clients_lock = threading.Lock()
_mjpeg_clients = 0


def _max_mjpeg_clients() -> int:
    try:
        return max(1, int(os.getenv("EVILEYE_MAX_MJPEG_CLIENTS", "8")))
    except Exception:
        return 8


def _acquire_mjpeg_slot() -> bool:
    global _mjpeg_clients
    with _mjpeg_clients_lock:
        if _mjpeg_clients >= _max_mjpeg_clients():
            return False
        _mjpeg_clients += 1
        return True


def _release_mjpeg_slot() -> None:
    global _mjpeg_clients
    with _mjpeg_clients_lock:
        _mjpeg_clients = max(0, _mjpeg_clients - 1)


def _touch_preview_demand(request: Request, rid: int, source_id: int | None = None) -> None:
    queue = getattr(request.app.state, "preview_demand_queue", None)
    if queue is None:
        return
    touched_at = time.time()
    try:
        key = f"{rid}:{source_id}" if source_id is not None else str(rid)
        queue.put_nowait((key, touched_at))
        if source_id is not None:
            queue.put_nowait((str(rid), touched_at))
    except Exception:
        return


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


def _source_count(run_info: dict) -> int:
    sources = run_info.get("sources")
    if isinstance(sources, list) and sources:
        return len(sources)
    summary = get_run_summary(int(run_info.get("id") or 0))
    if summary and isinstance(summary.get("sources"), list):
        return len(summary["sources"])
    return 0


def _require_source_id_if_multi(run_info: dict, source_id: int | None) -> None:
    if source_id is None and _source_count(run_info) > 1:
        raise HTTPException(
            status_code=400,
            detail="Multiple sources: specify source_id query parameter",
        )


def _load_latest_frame(run_info: dict, *, source_id: int | None = None) -> bytes | None:
    run_id_str = str(run_info["id"])
    broker_key = f"{run_id_str}:{source_id}" if source_id is not None else run_id_str
    broker = get_frame_broker()
    data = broker.latest_jpeg(broker_key)
    if not data and source_id is not None:
        data = broker.latest_jpeg(run_id_str)
    if data:
        return data
    return None


def _web_stream_available(run_info: dict, *, source_id: int | None = None, has_frame: bool | None = None) -> bool:
    if has_frame is None:
        has_frame = _load_latest_frame(run_info, source_id=source_id) is not None
    return bool(run_info.get("state") == "running" and has_frame)


def _stream_status_payload(rid: int, run_info: dict, *, source_id: int | None = None) -> dict:
    run_id_str = str(run_info["id"])
    stream_key = f"{run_id_str}:{source_id}" if source_id is not None else run_id_str
    is_active = get_frame_broker().is_stream_active(stream_key)
    has_frame = _load_latest_frame(run_info, source_id=source_id) is not None
    web_stream_available = _web_stream_available(run_info, source_id=source_id, has_frame=has_frame)
    return {
        "run_id": rid,
        "pipeline_id": rid,
        "source_id": source_id,
        "stream_active": is_active,
        "has_frame": has_frame,
        "web_stream_available": web_stream_available,
        "frame_dir_configured": True,
    }


async def _snapshot_impl(request: Request, rid: int, source_id: int | None = None):
    """
    Return the latest available JPEG snapshot for the given runtime.
    """
    _touch_preview_demand(request, rid, source_id=source_id)
    run_info = _resolve_run(rid)
    _require_source_id_if_multi(run_info, source_id)
    data = _load_latest_frame(run_info, source_id=source_id)
    if not data:
        raise HTTPException(status_code=404, detail="No frame available")
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@router.get("/runs/{rid}/snapshot")
async def snapshot(request: Request, rid: int, source_id: int | None = Query(None)):
    return await _snapshot_impl(request, rid, source_id=source_id)


@router.get("/pipelines/{rid}/snapshot", deprecated=True)
async def snapshot_legacy(request: Request, rid: int, source_id: int | None = Query(None)):
    return await _snapshot_impl(request, rid, source_id=source_id)


async def _mjpeg_generator(
        run_info: dict,
        fps: int,
        stop_event: threading.Event,
        source_id: int | None = None,
        *,
        stream_key: str,
        idle_sec: float = 8.0,
) -> AsyncGenerator[bytes, None]:
    boundary = b"--frame"
    delay = 1.0 / max(1, fps)
    no_frame_since = time.monotonic()
    broker = get_frame_broker()

    try:
        while not stop_event.is_set():
            data = _load_latest_frame(run_info, source_id=source_id)
            if data:
                no_frame_since = time.monotonic()
                yield (
                        boundary
                        + b"\r\n"
                        + b"Content-Type: image/jpeg\r\n\r\n"
                        + data
                        + b"\r\n"
                )
            elif time.monotonic() - no_frame_since > idle_sec:
                break

            elapsed = 0.0
            check_interval = 0.1
            while elapsed < delay and not stop_event.is_set():
                await asyncio.sleep(min(check_interval, delay - elapsed))
                elapsed += check_interval
    finally:
        _release_mjpeg_slot()
        try:
            broker.release_stream(stream_key)
        except Exception:
            pass


async def _mjpeg_stream_impl(
        request: Request,
        rid: int,
        source_id: int | None = None,
        fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    """
    MJPEG streaming endpoint.
    Sends a sequence of JPEG images in a single HTTP response.
    Browsers and players render it as a video stream thanks to
    'multipart/x-mixed-replace' and boundary markers.
    """
    _touch_preview_demand(request, rid, source_id=source_id)
    run_info = _resolve_run(rid)
    _require_source_id_if_multi(run_info, source_id)
    if not _web_stream_available(run_info, source_id=source_id):
        raise HTTPException(
            status_code=409,
            detail="Web stream is unavailable for this run. Preview relay is not delivering frames.",
        )
    if not _acquire_mjpeg_slot():
        raise HTTPException(
            status_code=503,
            detail=f"Too many MJPEG clients (limit={_max_mjpeg_clients()})",
        )
    run_id_str = str(run_info["id"])
    stream_key = f"{run_id_str}:{source_id}" if source_id is not None else run_id_str
    stop_event = get_frame_broker().acquire_stream(stream_key)
    idle_sec = float(os.getenv("EVILEYE_MJPEG_IDLE_SEC", "8") or 8)

    return StreamingResponse(
        _mjpeg_generator(
            run_info, fps, stop_event, source_id=source_id, stream_key=stream_key, idle_sec=idle_sec,
        ),
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
        request: Request,
        rid: int,
        source_id: int | None = Query(None),
        fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    return await _mjpeg_stream_impl(request, rid, source_id=source_id, fps=fps)


@router.get("/pipelines/{rid}/stream.mjpg", deprecated=True)
async def mjpeg_stream_legacy(
        request: Request,
        rid: int,
        source_id: int | None = Query(None),
        fps: int = Query(5, ge=1, le=60, description="Frames per second (1–60)"),
):
    return await _mjpeg_stream_impl(request, rid, source_id=source_id, fps=fps)


async def _stop_stream_impl(rid: int, source_id: int | None = None, force: bool = False):
    """
    Soft stop is a no-op: each MJPEG generator releases its own ref on disconnect.
    force=true hard-stops all consumers for the stream key.
    """
    run_info = _resolve_run(rid)
    run_id_str = str(run_info["id"])
    stream_key = f"{run_id_str}:{source_id}" if source_id is not None else run_id_str
    if not force:
        return {
            "run_id": rid,
            "pipeline_id": rid,
            "status": "noop",
            "message": "Soft stop is a no-op; MJPEG disconnect releases the consumer ref",
        }
    stopped = get_frame_broker().release_stream(stream_key, force=True)
    if stopped:
        return {
            "run_id": rid,
            "pipeline_id": rid,
            "status": "stopped",
            "message": f"Stream for run '{rid}' has been force-stopped",
        }
    return {
        "run_id": rid,
        "pipeline_id": rid,
        "status": "not_found",
        "message": f"No active stream found for run '{rid}'",
    }


@router.post("/runs/{rid}/stream:stop")
async def stop_stream(
    rid: int,
    source_id: int | None = Query(None),
    force: bool = Query(False),
):
    return await _stop_stream_impl(rid, source_id=source_id, force=force)


@router.post("/pipelines/{rid}/stream:stop", deprecated=True)
async def stop_stream_legacy(
    rid: int,
    source_id: int | None = Query(None),
    force: bool = Query(False),
):
    return await _stop_stream_impl(rid, source_id=source_id, force=force)


async def _stream_status_impl(request: Request, rid: int, source_id: int | None = None):
    """
    Get the status of the stream for the given run.
    """
    _touch_preview_demand(request, rid, source_id=source_id)
    run_info = _resolve_run(rid)
    _require_source_id_if_multi(run_info, source_id)
    return _stream_status_payload(rid, run_info, source_id=source_id)


@router.get("/runs/{rid}/stream:status")
async def stream_status(request: Request, rid: int, source_id: int | None = Query(None)):
    return await _stream_status_impl(request, rid, source_id=source_id)


@router.get("/pipelines/{rid}/stream:status", deprecated=True)
async def stream_status_legacy(request: Request, rid: int, source_id: int | None = Query(None)):
    return await _stream_status_impl(request, rid, source_id=source_id)


@router.get("/runs/{rid}/metadata")
async def stream_metadata(rid: int, source_id: int | None = Query(None)):
    run_info = _resolve_run(rid)
    _require_source_id_if_multi(run_info, source_id)
    key = f"{run_info['id']}:{source_id}" if source_id is not None else str(run_info["id"])
    meta = get_frame_broker().latest_metadata(key) or get_frame_broker().latest_metadata(str(run_info["id"])) or {}
    return {
        "run_id": rid,
        "source_id": source_id,
        "ts": meta.get("ts") or meta.get("timestamp"),
        "objects": meta.get("objects") or [],
        "zones": meta.get("zones") or [],
        "signalization": bool(meta.get("signalization")),
    }
