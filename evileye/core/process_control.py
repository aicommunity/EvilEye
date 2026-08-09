"""Cross-platform process tree termination and discovery."""

from __future__ import annotations

import logging
import os
import re
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import List, Optional, Sequence

try:
    import psutil
except ImportError:  # pragma: no cover
    psutil = None  # type: ignore

_logger = logging.getLogger(__name__)


def is_zombie(pid: int) -> bool:
    """Return True if ``pid`` exists but is a zombie (exited, not yet reaped)."""
    if pid <= 0:
        return False
    if psutil is not None:
        try:
            return psutil.Process(pid).status() == psutil.STATUS_ZOMBIE
        except (psutil.Error, TypeError, ValueError):
            pass
    try:
        status = Path(f"/proc/{pid}/status").read_text(encoding="utf-8", errors="ignore")
        for line in status.splitlines():
            if line.startswith("State:"):
                # e.g. "State:\tZ (zombie)"
                return " Z" in line or line.rstrip().endswith("Z")
    except OSError:
        pass
    return False


def _process_group_has_live_members(pgid: int) -> bool:
    """True if any non-zombie process still belongs to ``pgid``."""
    if pgid <= 0:
        return False

    if psutil is not None:
        for proc in psutil.process_iter(["pid"]):
            try:
                pid = int(proc.info["pid"])
                if pid <= 0:
                    continue
                if os.getpgid(pid) != pgid:
                    continue
                if is_zombie(pid):
                    continue
                return True
            except (psutil.Error, ProcessLookupError, PermissionError, OSError, TypeError, ValueError, KeyError):
                continue
        return False

    # /proc fallback without psutil
    try:
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit():
                continue
            pid = int(entry.name)
            try:
                if os.getpgid(pid) != pgid:
                    continue
            except (ProcessLookupError, PermissionError, OSError):
                continue
            if is_zombie(pid):
                continue
            return True
    except OSError:
        # If we cannot scan, fall back to killpg probe (treat unknown as alive)
        try:
            os.killpg(pgid, 0)
            return True
        except ProcessLookupError:
            return False
        except OSError:
            return False
    return False


def terminate_tree(pid: int, *, grace_sec: float = 5.0) -> None:
    """Terminate ``pid`` and its descendants.

    POSIX prefers process-group kill when available; Windows uses psutil / taskkill.

    Zombie-only process groups are treated as gone so a parent waiting to ``wait()``/
    reap the leader is not blocked for the full grace period.
    """
    if pid <= 0:
        return

    if sys.platform.startswith("win"):
        _terminate_tree_windows(pid, grace_sec=grace_sec)
        return

    # Prefer process group when the child was started with start_new_session
    try:
        pgid = os.getpgid(pid)
        if pgid > 0:
            try:
                os.killpg(pgid, signal.SIGTERM)
            except ProcessLookupError:
                return
            deadline = time.time() + grace_sec
            while time.time() < deadline:
                if not _process_group_has_live_members(pgid):
                    return
                time.sleep(0.1)
            if not _process_group_has_live_members(pgid):
                return
            _logger.warning(
                "Process group %s (leader pid=%s) did not exit after SIGTERM within %.1fs, sending SIGKILL",
                pgid,
                pid,
                grace_sec,
            )
            try:
                os.killpg(pgid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            return
    except (ProcessLookupError, PermissionError, OSError):
        pass

    _terminate_tree_psutil(pid, grace_sec=grace_sec)


def _terminate_tree_windows(pid: int, *, grace_sec: float) -> None:
    if psutil is not None:
        _terminate_tree_psutil(pid, grace_sec=grace_sec)
        return
    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass


def _terminate_tree_psutil(pid: int, *, grace_sec: float) -> None:
    if psutil is None:
        try:
            os.kill(pid, signal.SIGTERM)
        except OSError:
            pass
        return
    try:
        parent = psutil.Process(pid)
    except psutil.Error:
        return
    children = parent.children(recursive=True)
    procs = children + [parent]
    for proc in procs:
        try:
            proc.terminate()
        except psutil.Error:
            pass
    gone, alive = psutil.wait_procs(procs, timeout=grace_sec)
    for proc in alive:
        try:
            proc.kill()
        except psutil.Error:
            pass
    if sys.platform.startswith("win") and alive:
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(pid)],
                check=False,
                capture_output=True,
            )
        except Exception:
            pass


def find_pids_by_cmdline_regex(patterns: Sequence[str]) -> List[int]:
    """Return PIDs whose cmdline matches any of the regex patterns (search)."""
    if psutil is None:
        return []
    compiled = [re.compile(p) for p in patterns]
    found: List[int] = []
    for proc in psutil.process_iter(["pid", "cmdline"]):
        try:
            cmdline = proc.info.get("cmdline") or []
            text = " ".join(str(x) for x in cmdline)
            if not text:
                continue
            if any(c.search(text) for c in compiled):
                found.append(int(proc.info["pid"]))
        except (psutil.Error, TypeError, ValueError):
            continue
    return found


def pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if psutil is not None:
        return psutil.pid_exists(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def process_cmdline(pid: int) -> Optional[str]:
    if psutil is not None:
        try:
            return " ".join(psutil.Process(pid).cmdline())
        except psutil.Error:
            return None
    # Linux /proc fallback
    try:
        raw = open(f"/proc/{pid}/cmdline", "rb").read()
        return raw.replace(b"\x00", b" ").decode("utf-8", errors="replace").strip()
    except OSError:
        return None
