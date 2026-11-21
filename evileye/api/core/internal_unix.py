"""Loopback Unix-socket frame ingest (no HTTP/TLS; does not share uvicorn accept)."""
from __future__ import annotations

import hmac
import json
import socket
import struct
import threading
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.core.paths import runtime_dir

logger = get_module_logger("api.internal_unix")

_MAX_FRAME_BYTES = 8 * 1024 * 1024
_HEADER = struct.Struct("!I")
_stop = threading.Event()
_thread: Optional[threading.Thread] = None
_listen_sock: Optional[socket.socket] = None
_expected_token = ""


def internal_socket_path() -> Path:
    return runtime_dir() / "internal.sock"


def internal_relay_target_url() -> str:
    """Unix relay address for outbound frame publish (socket may not exist yet)."""
    return f"unix://{internal_socket_path()}"


def internal_relay_url() -> str | None:
    path = internal_socket_path()
    if path.exists() and path.is_socket():
        return internal_relay_target_url()
    return None


def encode_frame_packet(
    *,
    token: str,
    rid: int | str,
    source_id: int | None,
    jpeg_bytes: bytes,
    metadata: dict | None,
) -> bytes:
    header = json.dumps(
        {
            "token": token or "",
            "rid": int(rid),
            "source_id": source_id,
            "metadata": metadata or {},
        },
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    return _HEADER.pack(len(header)) + header + _HEADER.pack(len(jpeg_bytes)) + jpeg_bytes


def _recvall(conn: socket.socket, n: int) -> bytes:
    chunks: list[bytes] = []
    left = n
    while left > 0:
        piece = conn.recv(left)
        if not piece:
            raise ConnectionError("peer closed")
        chunks.append(piece)
        left -= len(piece)
    return b"".join(chunks)


def _handle_conn(conn: socket.socket) -> None:
    from evileye.api.routes.internal import ingest_frame_bytes

    conn.settimeout(2.0)
    while not _stop.is_set():
        raw_hlen = _recvall(conn, _HEADER.size)
        (hlen,) = _HEADER.unpack(raw_hlen)
        if hlen <= 0 or hlen > 256 * 1024:
            return
        header = json.loads(_recvall(conn, hlen).decode("utf-8"))
        (jlen,) = _HEADER.unpack(_recvall(conn, _HEADER.size))
        if jlen <= 0 or jlen > _MAX_FRAME_BYTES:
            return
        jpeg = _recvall(conn, jlen)
        supplied = str(header.get("token") or "")
        expected = _expected_token
        if not expected or len(supplied) != len(expected) or not hmac.compare_digest(supplied, expected):
            continue
        extra = header.get("metadata")
        if not isinstance(extra, dict):
            extra = None
        sid = header.get("source_id")
        try:
            sid = int(sid) if sid is not None else None
        except (TypeError, ValueError):
            sid = None
        ingest_frame_bytes(
            int(header.get("rid") or 0),
            jpeg,
            source_id=sid,
            extra=extra,
            content_type="image/jpeg",
        )


def _serve() -> None:
    assert _listen_sock is not None
    while not _stop.is_set():
        try:
            _listen_sock.settimeout(0.5)
            conn, _addr = _listen_sock.accept()
        except socket.timeout:
            continue
        except OSError:
            if _stop.is_set():
                break
            continue
        try:
            _handle_conn(conn)
        except Exception:
            pass
        finally:
            try:
                conn.close()
            except OSError:
                pass


def start_internal_unix_server(token: str) -> None:
    global _thread, _listen_sock, _expected_token
    stop_internal_unix_server()
    _stop.clear()
    _expected_token = token or ""
    path = internal_socket_path()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
    path.parent.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.bind(str(path))
    sock.listen(128)
    try:
        path.chmod(0o600)
    except OSError:
        pass
    _listen_sock = sock
    _thread = threading.Thread(target=_serve, daemon=True, name="InternalUnixRelay")
    _thread.start()
    logger.info("Internal frame relay socket: %s", path)


def stop_internal_unix_server() -> None:
    global _thread, _listen_sock
    _stop.set()
    sock = _listen_sock
    _listen_sock = None
    if sock is not None:
        try:
            sock.close()
        except OSError:
            pass
    if _thread is not None and _thread.is_alive():
        _thread.join(timeout=1.5)
    _thread = None
    path = internal_socket_path()
    try:
        if path.exists():
            path.unlink()
    except OSError:
        pass
