from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path
from threading import Lock

from evileye.core.paths import runtime_dir
from evileye.core.process_control import pid_exists as _pc_pid_exists
from evileye.core.process_control import process_cmdline, terminate_tree

_LOCK = Lock()


def _registry_dir() -> Path:
    path = runtime_dir() / "mp_sessions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _session_id() -> str | None:
    return os.getenv("EVILEYE_SESSION_ID")


def _session_file(session_id: str) -> Path:
    return _registry_dir() / f"{session_id}.json"


def _read_json(path: Path) -> dict:
    try:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _write_json(path: Path, data: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _pid_exists(pid: int) -> bool:
    return _pc_pid_exists(pid)


def _cmdline(pid: int) -> str:
    text = process_cmdline(pid)
    return text or ""


def _is_evileye_python_process(pid: int) -> bool:
    cmd = _cmdline(pid).lower()
    if not cmd:
        return False
    return ("python" in cmd) and ("evileye" in cmd)


def _is_zombie(pid: int) -> bool:
    try:
        import psutil

        return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
    except Exception:
        pass
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="ignore")
        for line in status.splitlines():
            if line.startswith("State:"):
                return " Z" in line or line.rstrip().endswith("Z")
    except Exception:
        pass
    return False


def _is_active_evileye_owner(pid: int) -> bool:
    if not pid or not _pid_exists(pid):
        return False
    if _is_zombie(pid):
        return False
    return _is_evileye_python_process(pid)


def _terminate_pid(pid: int, timeout_sec: float = 2.0) -> bool:
    if not _pid_exists(pid):
        return True
    if sys.platform.startswith("win"):
        terminate_tree(pid, grace_sec=timeout_sec)
        return not _pid_exists(pid)
    try:
        os.kill(pid, signal.SIGTERM)
    except Exception:
        return False
    deadline = time.monotonic() + max(0.1, timeout_sec)
    while time.monotonic() < deadline:
        if not _pid_exists(pid):
            return True
        time.sleep(0.05)
    try:
        os.kill(pid, signal.SIGKILL)
    except Exception:
        return not _pid_exists(pid)
    return not _pid_exists(pid)


def register_worker_pid(pid: int, worker_name: str) -> None:
    sid = _session_id()
    if not sid or not pid:
        return
    with _LOCK:
        path = _session_file(sid)
        payload = _read_json(path)
        if not payload:
            payload = {
                "session_id": sid,
                "owner_pid": os.getpid(),
                "started_at": time.time(),
                "workers": {},
            }
        workers = payload.setdefault("workers", {})
        workers[str(int(pid))] = {
            "worker_name": worker_name,
            "registered_at": time.time(),
        }
        _write_json(path, payload)


def unregister_worker_pid(pid: int) -> None:
    sid = _session_id()
    if not sid or not pid:
        return
    with _LOCK:
        path = _session_file(sid)
        payload = _read_json(path)
        workers = payload.get("workers", {})
        workers.pop(str(int(pid)), None)
        payload["workers"] = workers
        _write_json(path, payload)


def cleanup_current_session_workers() -> int:
    """
    Best-effort cleanup of remaining workers from current EVILEYE_SESSION_ID.
    Returns number of terminated processes.
    """
    sid = _session_id()
    if not sid:
        return 0
    with _LOCK:
        path = _session_file(sid)
        payload = _read_json(path)
        workers = payload.get("workers", {})
        killed = 0
        for pid_str in list(workers.keys()):
            try:
                pid = int(pid_str)
            except Exception:
                continue
            if _pid_exists(pid) and _is_evileye_python_process(pid):
                if _terminate_pid(pid):
                    killed += 1
            workers.pop(pid_str, None)
        payload["workers"] = workers
        _write_json(path, payload)
        return killed


def cleanup_session_by_id(session_id: str) -> int:
    """Terminate workers registered under a specific session id."""
    if not session_id:
        return 0
    with _LOCK:
        path = _session_file(session_id)
        payload = _read_json(path)
        if not payload:
            return 0
        workers = payload.get("workers", {})
        killed = 0
        for pid_str in list(workers.keys()):
            try:
                pid = int(pid_str)
            except Exception:
                continue
            if _pid_exists(pid) and _is_evileye_python_process(pid):
                if _terminate_pid(pid):
                    killed += 1
            workers.pop(pid_str, None)
        payload["workers"] = workers
        _write_json(path, payload)
        return killed


def cleanup_stale_sessions() -> int:
    """
    Cleanup orphaned worker processes from stale EvilEye sessions.
    Safety:
    - never touches non-Python or non-EvilEye processes
    - skips sessions whose owner_pid is still alive with evileye cmdline
    """
    current_sid = _session_id()
    killed_total = 0
    with _LOCK:
        for path in _registry_dir().glob("*.json"):
            payload = _read_json(path)
            sid = str(payload.get("session_id") or path.stem)
            if current_sid and sid == current_sid:
                continue
            owner_pid = int(payload.get("owner_pid") or 0)
            owner_alive = _is_active_evileye_owner(owner_pid)
            if owner_alive:
                # Another active EvilEye run; do not touch.
                continue
            workers = payload.get("workers", {})
            for pid_str in list(workers.keys()):
                try:
                    pid = int(pid_str)
                except Exception:
                    continue
                if _pid_exists(pid) and _is_evileye_python_process(pid):
                    if _terminate_pid(pid):
                        killed_total += 1
                workers.pop(pid_str, None)
            payload["workers"] = workers
            _write_json(path, payload)
    return killed_total
