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
        # Client metadata wins for overlay fields; keep transport tag.
        for key, value in extra.items():
            if key == "transport":
                continue
            meta[key] = value
        if source_id is not None:
            meta["source_id"] = source_id
    return meta


@router.post("/frames/{rid}")
async def receive_frame(rid: int, request: Request, source_id: int | None = Query(None)) -> dict:
    """Accept JPEG (+ optional overlay metadata) from runtime process."""
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
            body = await frame_field.read()
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

    if not body:
        raise HTTPException(status_code=400, detail="Empty body")

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
    }
