"""Loopback Unix-socket control channel (API -> running controller)."""
from __future__ import annotations

import json
import socket
import threading
from pathlib import Path
from typing import Any, Callable

from evileye.core.logger import get_module_logger
from evileye.core.paths import runtime_dir

logger = get_module_logger("api.control_ipc")

_CONTROL_SOCKET = "control.sock"
_MAX_PAYLOAD_BYTES = 256 * 1024


def control_socket_path() -> Path:
    return runtime_dir() / _CONTROL_SOCKET


def send_control_command(command: dict[str, Any], *, timeout: float = 2.0) -> dict[str, Any]:
    """Send a JSON control command to the running controller process."""
    path = control_socket_path()
    if not path.exists():
        return {"ok": False, "error": "control_socket_missing"}
    payload = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    if len(payload) > _MAX_PAYLOAD_BYTES:
        return {"ok": False, "error": "payload_too_large"}
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    sock.settimeout(timeout)
    try:
        sock.connect(str(path))
        sock.sendall(payload)
        sock.shutdown(socket.SHUT_WR)
        chunks: list[bytes] = []
        while True:
            try:
                piece = sock.recv(4096)
            except socket.timeout:
                break
            if not piece:
                break
            chunks.append(piece)
        if not chunks:
            return {"ok": False, "error": "empty_response"}
        return json.loads(b"".join(chunks).decode("utf-8"))
    except FileNotFoundError:
        return {"ok": False, "error": "control_socket_missing"}
    except json.JSONDecodeError:
        return {"ok": False, "error": "invalid_response"}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}
    finally:
        try:
            sock.close()
        except OSError:
            pass


class ControlIpcServer:
    def __init__(self) -> None:
        self._sock: socket.socket | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._handler: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def start(self, handler: Callable[[dict[str, Any]], dict[str, Any]]) -> None:
        self.stop()
        self._handler = handler
        self._stop.clear()
        path = control_socket_path()
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass
        path.parent.mkdir(parents=True, exist_ok=True)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.bind(str(path))
        sock.listen(8)
        try:
            path.chmod(0o600)
        except OSError:
            pass
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, daemon=True, name="ControlIpcServer")
        self._thread.start()
        logger.info("Control IPC socket: %s", path)

    def stop(self) -> None:
        self._stop.set()
        sock = self._sock
        self._sock = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        self._thread = None
        path = control_socket_path()
        try:
            if path.exists():
                path.unlink()
        except OSError:
            pass

    def _serve(self) -> None:
        assert self._sock is not None
        while not self._stop.is_set():
            try:
                self._sock.settimeout(0.5)
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                if self._stop.is_set():
                    break
                continue
            try:
                self._handle_conn(conn)
            finally:
                try:
                    conn.close()
                except OSError:
                    pass

    def _handle_conn(self, conn: socket.socket) -> None:
        conn.settimeout(2.0)
        chunks: list[bytes] = []
        while True:
            piece = conn.recv(4096)
            if not piece:
                break
            chunks.append(piece)
            if sum(len(c) for c in chunks) > _MAX_PAYLOAD_BYTES:
                return
        if not chunks or self._handler is None:
            return
        try:
            command = json.loads(b"".join(chunks).decode("utf-8"))
        except json.JSONDecodeError:
            conn.sendall(json.dumps({"ok": False, "error": "invalid_json"}).encode("utf-8"))
            return
        if not isinstance(command, dict):
            conn.sendall(json.dumps({"ok": False, "error": "invalid_command"}).encode("utf-8"))
            return
        try:
            response = self._handler(command)
        except Exception as exc:
            logger.warning("Control command failed: %s", exc, exc_info=True)
            response = {"ok": False, "error": str(exc)}
        if not isinstance(response, dict):
            response = {"ok": False, "error": "invalid_handler_response"}
        conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
