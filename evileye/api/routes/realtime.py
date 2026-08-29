"""WebSocket metadata stream backed by FrameBroker (cross-process safe)."""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Optional, Callable

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from evileye.api.core.config_run_access import get_config_run_manager
from evileye.api.core.live_preview_hub import get_live_preview_hub
from evileye.api.core.runtime_registry import load_runtime_record
from evileye.api.security import current_user, load_web_auth_config, permissions_for_role
from evileye.core.runtime_services import get_frame_broker

logger = logging.getLogger("evileye.api.realtime")
router = APIRouter(prefix="/api/v1", tags=["realtime"])

_WS_MIN_INTERVAL_SEC = 0.5


def _touch_preview_demand_ws(
    websocket: WebSocket,
    rid: int,
    level: str = "grid",
    *,
    force: bool = False,
    source_id: int | None = None,
) -> None:
    queue = getattr(websocket.app.state, "preview_demand_queue", None)
    if queue is None:
        return
    touched_at = time.time()
    normalized_level = (level or "grid").strip().lower()
    if normalized_level not in {"grid", "stream"}:
        normalized_level = "grid"
    try:
        if source_id is not None:
            queue.put_nowait((f"{rid}:{source_id}", touched_at, normalized_level, force))
        queue.put_nowait((str(rid), touched_at, normalized_level, force))
    except Exception:
        pass


def make_hub_demand_callback(app) -> Callable[[int], None]:
    def _cb(run_id: int) -> None:
        queue = getattr(app.state, "preview_demand_queue", None)
        if queue is None:
            return
        try:
            queue.put_nowait((str(run_id), time.time(), "grid", False))
        except Exception:
            pass

    return _cb


async def _authorize_live_ws(websocket: WebSocket) -> bool:
    from evileye.api.core.ip_ban_store import get_ip_ban_store
    from evileye.api.core.rate_guard import get_rate_guard

    guard = get_rate_guard()
    ip = guard.client_ip(websocket)
    if get_ip_ban_store().is_banned(ip):
        logger.warning("ws rejected code=4403 reason=banned bucket=ws_live_grid ip=%s", ip)
        guard.note_ws_reject("banned")
        await websocket.close(code=4403)
        return False
    if guard.record_ws_connect(websocket, bucket="ws_live_grid"):
        logger.warning("ws rejected code=4403 reason=ws_live_flood bucket=ws_live_grid ip=%s", ip)
        await websocket.close(code=4403)
        return False

    auth = load_web_auth_config()
    if not auth.enabled:
        return True
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
        return False
    granted = set(user.get("permissions") or permissions_for_role(str(user.get("role") or "user")))
    if "live:view" not in granted and "system:admin" not in granted:
        logger.warning("ws rejected code=4403 reason=permission bucket=ws_live_grid ip=%s", ip)
        guard.note_ws_reject("permission")
        await websocket.close(code=4403)
        return False
    return True


def _camera_access_from_websocket(websocket: WebSocket):
    from evileye.api.core.camera_access import CameraAccess, lookup_user_record
    from evileye.api.core.user_prefs import allowed_cameras_from_record, prefs_from_record, normalize_allowed_cameras
    from evileye.api.security import normalize_role

    auth = load_web_auth_config()
    if not auth.enabled:
        return CameraAccess(unrestricted=True, allowed_names=frozenset(), visible_names=None)
    session = websocket.scope.get("session") or {}
    raw = session.get("user") if isinstance(session, dict) else None
    if not isinstance(raw, dict):
        try:
            raw = current_user(websocket)  # type: ignore[arg-type]
        except Exception:
            raw = None
    if not isinstance(raw, dict):
        return CameraAccess(unrestricted=False, allowed_names=frozenset(), visible_names=frozenset())

    # Build a minimal request-like access from session user
    role = normalize_role(str(raw.get("role") or "user"))
    username = str(raw.get("username") or "")
    record = lookup_user_record(username) if username else None
    prefs = prefs_from_record(record)
    visible_raw = prefs.get("visible_cameras")
    visible_names = None if visible_raw is None else frozenset(normalize_allowed_cameras(visible_raw))
    if role == "admin":
        return CameraAccess(unrestricted=True, allowed_names=frozenset(), visible_names=visible_names)
    return CameraAccess(
        unrestricted=False,
        allowed_names=frozenset(allowed_cameras_from_record(record)),
        visible_names=visible_names,
    )


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
    from evileye.api.core.ip_ban_store import get_ip_ban_store
    from evileye.api.core.rate_guard import get_rate_guard

    guard = get_rate_guard()
    ip = guard.client_ip(websocket)
    if get_ip_ban_store().is_banned(ip):
        logger.warning("ws rejected code=4403 reason=banned bucket=ws_metadata ip=%s", ip)
        guard.note_ws_reject("banned")
        await websocket.close(code=4403)
        return
    if guard.record_ws_connect(websocket, bucket="ws_metadata"):
        logger.warning("ws rejected code=4403 reason=ws_metadata_flood bucket=ws_metadata ip=%s", ip)
        await websocket.close(code=4403)
        return

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
            logger.warning("ws rejected code=4403 reason=permission bucket=ws_metadata ip=%s", ip)
            guard.note_ws_reject("permission")
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

    from evileye.api.core.camera_access import assert_source_id_allowed

    access = _camera_access_from_websocket(websocket)
    try:
        assert_source_id_allowed(access, int(run_info["id"]), source_id)
    except Exception:
        await websocket.close(code=4403)
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
                if source_id is None:
                    meta = broker.latest_metadata(str(rid))
                else:
                    # Do not fallback to run-level payload for source-scoped WS:
                    # this prevents cross-camera overlay leakage.
                    meta = broker.latest_metadata(key)
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


@router.websocket("/runs/{rid}/ws/live")
async def live_grid_preview_ws(websocket: WebSocket, rid: int):
    if not await _authorize_live_ws(websocket):
        return
    try:
        run_info = _resolve_run(rid)
    except KeyError:
        await websocket.close(code=4404)
        return
    if run_info.get("state") != "running":
        await websocket.close(code=4001)
        return

    hub = get_live_preview_hub()
    if len(hub._clients) >= hub._max_clients:
        await websocket.close(code=4429)
        return

    await websocket.accept()
    _touch_preview_demand_ws(websocket, rid, "grid")
    client = await hub.register(websocket, rid)
    if client is None:
        await websocket.close(code=4429)
        return

    from evileye.api.core.camera_access import allowed_source_ids_for_run

    access = _camera_access_from_websocket(websocket)
    allowed_ids = allowed_source_ids_for_run(access, int(run_info["id"]))

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            op = msg.get("op") or msg.get("subscribe")
            if op == "subscribe" or msg.get("subscribe") is not None:
                ids = msg.get("source_ids") or msg.get("subscribe") or []
                if isinstance(ids, list):
                    source_ids = [int(x) for x in ids]
                    if allowed_ids is not None:
                        if not source_ids:
                            source_ids = sorted(allowed_ids)
                        else:
                            source_ids = [sid for sid in source_ids if sid in allowed_ids]
                    hub.set_client_sources(client, source_ids)
                    for sid in source_ids:
                        _touch_preview_demand_ws(websocket, rid, "grid", source_id=sid)
            elif op == "ping":
                _touch_preview_demand_ws(websocket, rid, "grid")
                for sid in client.source_ids:
                    _touch_preview_demand_ws(websocket, rid, "grid", source_id=sid)
                await websocket.send_json({"op": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        hub.unregister(client)
