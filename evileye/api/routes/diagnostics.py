"""Client diagnostics ingest (browser event batches)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from evileye.api.core.client_debug import user_client_debug_enabled
from evileye.api.core.client_diag_log import append_client_diag_events
from evileye.api.security import require_authenticated

router = APIRouter(prefix="/api/v1/diagnostics", tags=["diagnostics"])

_MAX_EVENTS = 100
_MAX_BATCHES_PER_MIN = 30
_WINDOW_SEC = 60.0
_rate_lock = Lock()
_rate_by_user: dict[str, deque[float]] = defaultdict(deque)


class ClientDiagBatch(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=128)
    events: list[dict[str, Any]] = Field(default_factory=list)
    ua: str | None = Field(None, max_length=512)
    page: str | None = Field(None, max_length=64)
    user: str | None = Field(None, max_length=256)


def _rate_exceeded(username: str) -> bool:
    now = time.time()
    with _rate_lock:
        q = _rate_by_user[username]
        while q and (now - q[0]) > _WINDOW_SEC:
            q.popleft()
        if len(q) >= _MAX_BATCHES_PER_MIN:
            return True
        q.append(now)
        return False


@router.post("/client")
async def post_client_diagnostics(payload: ClientDiagBatch, request: Request) -> dict[str, Any]:
    user = require_authenticated(request)
    username = str(user.get("username") or "").strip() or "unknown"
    if _rate_exceeded(username):
        raise HTTPException(status_code=429, detail="Diagnostics rate limit exceeded")

    events = payload.events[:_MAX_EVENTS]
    # Always persist for allowlist users; others still accepted when manually enabled.
    force = user_client_debug_enabled(username)
    if not events and not force:
        return {"ok": True, "written": 0}

    written = append_client_diag_events(
        user=username,
        session_id=payload.session_id,
        events=events,
        ua=payload.ua,
        page=payload.page,
    )
    return {"ok": True, "written": written, "client_debug": force}
