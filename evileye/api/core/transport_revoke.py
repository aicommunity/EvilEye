"""Revoke long-lived transports for a username (F01 / R08)."""

from __future__ import annotations

import logging
import threading
from typing import Any, Callable
from weakref import WeakSet

logger = logging.getLogger("evileye.api.transport_revoke")

# Metadata WS: (websocket, username)
_metadata_lock = threading.Lock()
_metadata_clients: list[tuple[Any, str]] = []

# MJPEG: client_id -> {username, cancel: threading.Event}
_mjpeg_lock = threading.Lock()
_mjpeg_clients: dict[int, dict[str, Any]] = {}
_mjpeg_next_id = 1


def register_metadata_ws(websocket: Any, username: str | None) -> None:
    name = str(username or "").strip()
    if not name:
        return
    with _metadata_lock:
        _metadata_clients.append((websocket, name))


def unregister_metadata_ws(websocket: Any) -> None:
    with _metadata_lock:
        _metadata_clients[:] = [(ws, u) for ws, u in _metadata_clients if ws is not websocket]


def unregister_metadata_username(username: str) -> int:
    name = str(username or "").strip()
    if not name:
        return 0
    closed = 0
    with _metadata_lock:
        keep: list[tuple[Any, str]] = []
        to_close: list[Any] = []
        for ws, u in _metadata_clients:
            if u == name:
                to_close.append(ws)
            else:
                keep.append((ws, u))
        _metadata_clients[:] = keep
    for ws in to_close:
        try:
            close = getattr(ws, "close", None)
            if close is not None:
                result = close(code=4403)
                if hasattr(result, "__await__"):
                    # Best-effort: schedule if loop available via hub pattern.
                    try:
                        import asyncio

                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            loop.create_task(result)
                    except Exception:
                        pass
            closed += 1
        except Exception:
            pass
    return closed


def register_mjpeg_client(username: str | None) -> tuple[int, threading.Event]:
    """Register MJPEG stream; returns (client_id, cancel_event)."""
    global _mjpeg_next_id
    cancel = threading.Event()
    name = str(username or "").strip()
    with _mjpeg_lock:
        cid = _mjpeg_next_id
        _mjpeg_next_id += 1
        _mjpeg_clients[cid] = {"username": name, "cancel": cancel}
    return cid, cancel


def unregister_mjpeg_client(client_id: int) -> None:
    with _mjpeg_lock:
        _mjpeg_clients.pop(int(client_id), None)


def unregister_mjpeg_username(username: str) -> int:
    name = str(username or "").strip()
    if not name:
        return 0
    with _mjpeg_lock:
        ids = [cid for cid, info in _mjpeg_clients.items() if info.get("username") == name]
        for cid in ids:
            info = _mjpeg_clients.get(cid)
            if info is not None:
                try:
                    info["cancel"].set()
                except Exception:
                    pass
        return len(ids)


def revoke_user_transports(username: str) -> dict[str, int]:
    """Close preview WS, metadata WS, and cancel MJPEG for username."""
    name = str(username or "").strip()
    preview = 0
    metadata = 0
    mjpeg = 0
    if not name:
        return {"preview": 0, "metadata": 0, "mjpeg": 0}
    try:
        from evileye.api.core.live_preview_hub import get_live_preview_hub

        preview = int(get_live_preview_hub().unregister_username(name) or 0)
    except Exception as exc:
        logger.debug("preview revoke failed for %s: %s", name, exc)
    try:
        metadata = unregister_metadata_username(name)
    except Exception as exc:
        logger.debug("metadata revoke failed for %s: %s", name, exc)
    try:
        mjpeg = unregister_mjpeg_username(name)
    except Exception as exc:
        logger.debug("mjpeg revoke failed for %s: %s", name, exc)
    return {"preview": preview, "metadata": metadata, "mjpeg": mjpeg}
