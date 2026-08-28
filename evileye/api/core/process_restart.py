"""Safe pipeline restart helpers (avoid killing the API that serves the request)."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Optional

from evileye.core.logger import get_module_logger

logger = get_module_logger("api.process_restart")


def pid_is_alive(pid: int) -> bool:
    if not pid or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def iter_ancestor_pids(start_pid: int | None = None) -> list[int]:
    """Return [start, parent, ..., 1] using /proc (best-effort)."""
    pid = int(start_pid or os.getpid())
    out: list[int] = []
    seen: set[int] = set()
    while pid > 0 and pid not in seen:
        seen.add(pid)
        out.append(pid)
        try:
            with open(f"/proc/{pid}/status", encoding="utf-8") as fh:
                ppid = 0
                for line in fh:
                    if line.startswith("PPid:"):
                        ppid = int(line.split(":", 1)[1].strip())
                        break
        except Exception:
            break
        if ppid <= 0 or ppid == pid:
            break
        pid = ppid
    return out


def pid_hosts_current_process(target_pid: int) -> bool:
    """True if target_pid is this process or an ancestor (stopping it would kill the API)."""
    try:
        target = int(target_pid)
    except Exception:
        return False
    if target <= 0:
        return False
    return target in set(iter_ancestor_pids())


def read_cmdline(pid: int) -> list[str]:
    try:
        raw = Path(f"/proc/{pid}/cmdline").read_bytes()
    except Exception:
        return []
    if not raw:
        return []
    return [p.decode("utf-8", errors="ignore") for p in raw.split(b"\0") if p]


def cmdline_has_gui(argv: list[str]) -> bool:
    # Default process.py gui=True; managed starts use --no-gui.
    if "--no-gui" in argv:
        return False
    if "--gui" in argv:
        return True
    # Heuristic: explicit BooleanOptionalAction may omit --gui when default True.
    return "process.py" in " ".join(argv)


def cmdline_config_path(argv: list[str]) -> Optional[str]:
    for i, tok in enumerate(argv):
        if tok == "--config" and i + 1 < len(argv):
            return argv[i + 1]
        if tok.startswith("--config="):
            return tok.split("=", 1)[1]
    return None


def build_process_cmd(
    config_path: str | Path,
    *,
    gui: bool,
    autoclose: bool = False,
) -> list[str]:
    process_py = Path(__file__).resolve().parents[2] / "process.py"
    cmd = [
        sys.executable,
        str(process_py),
        "--config",
        str(config_path),
    ]
    cmd.append("--gui" if gui else "--no-gui")
    cmd.append("--autoclose" if autoclose else "--no-autoclose")
    return cmd


def spawn_detached_restart_helper(
    *,
    wait_pid: int,
    cmd: list[str],
    cwd: str | Path | None = None,
    grace_sec: float = 120.0,
) -> int:
    """
    Start a helper in a new session that waits for wait_pid to exit, then runs cmd.

    Returns helper PID.
    """
    workdir = str(cwd or Path.cwd())
    grace = max(5.0, float(grace_sec))
    # Keep helper tiny and dependency-free so it survives API death.
    helper = (
        "import os,sys,time,signal,subprocess\n"
        "wait_pid=int(sys.argv[1]); grace=float(sys.argv[2]); cwd=sys.argv[3]; cmd=sys.argv[4:]\n"
        "deadline=time.time()+grace\n"
        "while time.time()<deadline:\n"
        "  try:\n"
        "    os.kill(wait_pid,0)\n"
        "  except OSError:\n"
        "    break\n"
        "  time.sleep(0.4)\n"
        "else:\n"
        "  try:\n"
        "    if os.name=='nt':\n"
        "      subprocess.run(['taskkill','/F','/T','/PID',str(wait_pid)],check=False,"
        " capture_output=True)\n"
        "    else:\n"
        "      os.kill(wait_pid, signal.SIGKILL)\n"
        "  except Exception: pass\n"
        "  time.sleep(1.0)\n"
        "kwargs=dict(cwd=cwd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,"
        " stderr=subprocess.DEVNULL, close_fds=(os.name!='nt'))\n"
        "if os.name=='nt':\n"
        "  kwargs['creationflags']=getattr(subprocess,'CREATE_NEW_PROCESS_GROUP',0)\n"
        "else:\n"
        "  kwargs['start_new_session']=True\n"
        "subprocess.Popen(cmd, **kwargs)\n"
    )
    popen_kwargs: dict[str, Any] = {
        "cwd": workdir,
        "stdin": subprocess.DEVNULL,
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "close_fds": os.name != "nt",
    }
    if os.name == "nt":
        popen_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
    proc = subprocess.Popen(
        [sys.executable, "-c", helper, str(int(wait_pid)), str(grace), workdir, *cmd],
        **popen_kwargs,
    )
    logger.info(
        "Spawned restart helper pid=%s waiting for pid=%s then: %s",
        proc.pid,
        wait_pid,
        " ".join(cmd),
    )
    return int(proc.pid)


def signal_pid_term(pid: int) -> None:
    """Send SIGTERM to a single PID (not process group) for graceful controller shutdown."""
    os.kill(int(pid), signal.SIGTERM)


def _runtime_matches_config(rec: dict[str, Any], config_name: str) -> bool:
    want = Path(config_name).name
    if not want.endswith(".json"):
        want = f"{want}.json"
    path = str(rec.get("config_path") or "")
    base = Path(path).name if path else ""
    return base == want or path.endswith(want)


def _runtime_is_alive(rec: dict[str, Any]) -> bool:
    state = str(rec.get("state") or "")
    return bool(rec.get("alive")) or state in {"running", "starting"}


def find_all_matching_runtimes(
    records: dict[int, dict[str, Any]],
    config_name: str,
    *,
    site_dir: Path | None = None,
) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    for rec in records.values():
        if not isinstance(rec, dict):
            continue
        if not _runtime_matches_config(rec, config_name):
            continue
        if not _runtime_is_alive(rec):
            continue
        if site_dir is not None:
            from evileye.site_runtime_guard import record_belongs_to_site

            if not record_belongs_to_site(rec, site_dir):
                continue
        matches.append(rec)
    matches.sort(
        key=lambda r: (
            0 if r.get("managed") else 1,
            0 if r.get("source") == "web" else 1,
            -int(r.get("id") or 0),
        )
    )
    return matches


def find_matching_runtime(
    records: dict[int, dict[str, Any]],
    config_name: str,
    *,
    site_dir: Path | None = None,
) -> Optional[dict[str, Any]]:
    matches = find_all_matching_runtimes(records, config_name, site_dir=site_dir)
    return matches[0] if matches else None
