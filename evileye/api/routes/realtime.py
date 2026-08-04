"""WebSocket metadata stream backed by FrameBroker (cross-process safe)."""
from __future__ import annotations

import asyncio
import hashlib
import json
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.runtime_registry import load_runtime_record
from evileye.api.security import current_user, load_web_auth_config, permissions_for_role
from evileye.core.runtime_services import get_frame_broker

router = APIRouter(prefix="/api/v1", tags=["realtime"])

_WS_MIN_INTERVAL_SEC = 0.5


def _resolve_run(rid: int) -> dict:
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
        raise KeyError(rid)
    return run_info


def _payload_fingerprint(payload: dict) -> str:
    try:
        raw = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    except Exception:
        raw = str(payload)
    return hashlib.md5(raw.encode("utf-8", errors="ignore")).hexdigest()


@router.websocket("/runs/{rid}/ws")
async def run_metadata_ws(websocket: WebSocket, rid: int, source_id: Optional[int] = Query(None)):
    auth = load_web_auth_config()
    if auth.enabled:
        user = None
        try:
            user = current_user(websocket)  # type: ignore[arg-type]
        except Exception:
            user = None
        if user is None:
            session = websocket.scope.get("session") or {}
            raw = session.get("user") if isinstance(session, dict) else None
            if isinstance(raw, dict):
                user = raw
        if user is None:
            await websocket.close(code=4401)
            return
        granted = set(user.get("permissions") or permissions_for_role(str(user.get("role") or "user")))
        if "live:view" not in granted and "system:admin" not in granted:
            await websocket.close(code=4403)
            return

    try:
        run_info = _resolve_run(rid)
    except KeyError:
        await websocket.close(code=4404)
        return
    if run_info.get("state") != "running":
        await websocket.close(code=4001)
        return

    await websocket.accept()
    broker = get_frame_broker()
    key = f"{rid}:{source_id}" if source_id is not None else str(rid)
    q = broker.subscribe(key)
    last_fp: str | None = None
    last_sent = 0.0
    try:
        while True:
            meta = None
            try:
                meta = q.get_nowait()
            except Exception:
                meta = broker.latest_metadata(key) or broker.latest_metadata(str(rid))
            now = asyncio.get_event_loop().time()
            if meta is not None:
                payload = dict(meta)
                payload.setdefault("ts", payload.get("timestamp") or payload.get("ts"))
                payload.setdefault("source_id", source_id)
                payload.setdefault("objects", payload.get("objects") or [])
                payload.setdefault("zones", payload.get("zones") or [])
                fp = _payload_fingerprint(payload)
                if fp != last_fp or (now - last_sent) >= _WS_MIN_INTERVAL_SEC:
                    await websocket.send_json(payload)
                    last_fp = fp
                    last_sent = now
            await asyncio.sleep(0.1)
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        broker.unsubscribe(key, q)
