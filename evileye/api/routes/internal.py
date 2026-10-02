"""
Internal API: receive JPEG frames from external runtimes so streaming endpoints
work without file-based frame handoff.
"""
from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request

from evileye.core.runtime_services import get_frame_broker

router = APIRouter(prefix="/api/v1/internal", tags=["internal"], include_in_schema=False)

_MAX_FRAME_BYTES = 8 * 1024 * 1024


def _merge_metadata(
    *,
    source_id: int | None,
    content_type: str,
    extra: dict[str, Any] | None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "source_id": source_id,
        "content_type": content_type or "image/jpeg",
        "transport": "http_internal",
    }
    if extra:
        for key, value in extra.items():
            if key == "transport":
                continue
            meta[key] = value
        if source_id is not None:
            meta["source_id"] = source_id
    return meta


def _reject_oversized(request: Request) -> None:
    try:
        from evileye.api.core.rate_guard import get_rate_guard

        get_rate_guard().record_oversized_body(request)
    except Exception:
        pass
    raise HTTPException(status_code=413, detail="Frame body too large")


@router.post("/frames/{rid}")
async def receive_frame(rid: int, request: Request, source_id: int | None = Query(None)) -> dict:
    """Accept JPEG (+ optional overlay metadata) from runtime process."""
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > _MAX_FRAME_BYTES:
                _reject_oversized(request)
        except ValueError:
            pass

    content_type = request.headers.get("content-type", "image/jpeg")
    extra: dict[str, Any] | None = None
    body: bytes

    if "multipart/form-data" in content_type:
        form = await request.form()
        meta_field = form.get("metadata")
        if meta_field is not None:
            raw = meta_field if isinstance(meta_field, str) else (await meta_field.read()).decode("utf-8", errors="ignore")
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    extra = parsed
            except json.JSONDecodeError as exc:
                raise HTTPException(status_code=400, detail=f"Invalid metadata JSON: {exc}") from exc
        frame_field = form.get("frame")
        if frame_field is None:
            raise HTTPException(status_code=400, detail="Missing multipart field 'frame'")
        if hasattr(frame_field, "read"):
            body = await frame_field.read(_MAX_FRAME_BYTES + 1)
        else:
            body = bytes(frame_field)
        content_type = "image/jpeg"
    else:
        body = await request.body()
        hdr = request.headers.get("x-evileye-frame-metadata")
        if hdr:
            try:
                parsed = json.loads(hdr)
                if isinstance(parsed, dict):
                    extra = parsed
            except json.JSONDecodeError:
                pass

    if len(body) > _MAX_FRAME_BYTES:
        _reject_oversized(request)

    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

    return ingest_frame_bytes(rid, body, source_id=source_id, extra=extra, content_type=content_type)


def ingest_frame_bytes(
    rid: int | str,
    body: bytes,
    *,
    source_id: int | None,
    extra: dict[str, Any] | None,
    content_type: str,
) -> dict:
    metadata = _merge_metadata(source_id=source_id, content_type=content_type, extra=extra)
    broker = get_frame_broker()
    broker.publish_jpeg(str(rid), body, metadata=metadata)
    sid = metadata.get("source_id")
    if sid is not None:
        broker.publish_jpeg(f"{rid}:{sid}", body, metadata=metadata)
    return {
        "ok": True,
        "size": len(body),
        "source_id": sid,
        "has_objects": bool(metadata.get("objects")),
        "has_zones": bool(metadata.get("zones")),
        "preview_demand": preview_demand_active(rid),
    }


def preview_demand_active(rid: int | str | None = None) -> bool:
    """True when Live MJPEG/WS (or broker stream) currently wants frames."""
    try:
        from evileye.api.routes.streaming import mjpeg_clients_count

        if int(mjpeg_clients_count() or 0) > 0:
            return True
    except Exception:
        pass
    try:
        broker = get_frame_broker()
        if rid is not None and broker.is_stream_active(str(rid)):
            return True
        stats = broker.get_runtime_stats() if hasattr(broker, "get_runtime_stats") else {}
        if int(stats.get("active_streams") or 0) > 0:
            return True
    except Exception:
        pass
    try:
        from evileye.api.core.live_preview_hub import get_live_preview_hub

        hub = get_live_preview_hub()
        # Hub may expose different counters depending on build; treat any subscribers as demand.
        for attr in ("subscriber_count", "client_count", "ws_client_count"):
            fn = getattr(hub, attr, None)
            if callable(fn) and int(fn() or 0) > 0:
                return True
            val = getattr(hub, attr, None)
            if isinstance(val, int) and val > 0:
                return True
        subs = getattr(hub, "_subscribers", None)
        if isinstance(subs, dict) and len(subs) > 0:
            return True
    except Exception:
        pass
    return False


@router.get("/preview_demand")
async def get_preview_demand(rid: int | None = Query(None)) -> dict:
    """Pipeline-side poll: whether separate web clients currently need JPEG frames."""
    active = preview_demand_active(rid)
    mjpeg = None
    streams = None
    try:
        from evileye.api.routes.streaming import mjpeg_clients_count

        mjpeg = int(mjpeg_clients_count() or 0)
    except Exception:
        pass
    try:
        stats = get_frame_broker().get_runtime_stats()
        streams = int(stats.get("active_streams") or 0)
    except Exception:
        pass
    return {
        "ok": True,
        "active": bool(active),
        "mjpeg_clients": mjpeg,
        "active_streams": streams,
        "rid": rid,
    }
