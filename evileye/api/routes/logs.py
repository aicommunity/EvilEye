from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from evileye.api.core.log_service import list_log_files, read_log_file, read_log_tail_from_offset

router = APIRouter(prefix="/api/v1/logs", tags=["logs"])


@router.get("")
async def runtime_logs(limit: int = Query(50, ge=1, le=200)) -> dict:
    return list_log_files(limit=limit)


@router.get("/{filename}/stream")
async def runtime_log_stream(
    filename: str,
    tail: int = Query(200, ge=10, le=5000),
    interval: float = Query(2.0, ge=0.5, le=30.0),
):
    """SSE tail of a log file using byte-offset reads."""

    async def gen():
        # Seed with last N lines once, then stream by byte offset.
        try:
            seed = read_log_file(filename, tail=tail)
        except ValueError as exc:
            yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
            return
        except FileNotFoundError:
            yield f"event: error\ndata: {json.dumps({'detail': 'not found'})}\n\n"
            return

        content = seed.get("content") or ""
        offset = int(seed.get("size_bytes") or 0)
        yield f"data: {json.dumps({'name': seed['name'], 'content': content, 'updated_at': seed['updated_at']})}\n\n"

        while True:
            try:
                payload = read_log_tail_from_offset(filename, offset=offset)
            except ValueError as exc:
                yield f"event: error\ndata: {json.dumps({'detail': str(exc)})}\n\n"
                break
            except FileNotFoundError:
                yield f"event: error\ndata: {json.dumps({'detail': 'not found'})}\n\n"
                break
            chunk = payload.get("chunk") or ""
            offset = int(payload.get("next_offset") or offset)
            if chunk:
                yield f"data: {json.dumps({'name': payload['name'], 'append': chunk, 'content': chunk, 'updated_at': payload['updated_at']})}\n\n"
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(interval)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.get("/{filename}")
async def runtime_log_content(
        filename: str,
        tail: int | None = Query(None, ge=10, le=5000),
) -> dict:
    try:
        return read_log_file(filename, tail=tail)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Log file not found") from None
