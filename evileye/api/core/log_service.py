from __future__ import annotations

from datetime import datetime
from pathlib import Path
import re
from typing import Any, Optional

from evileye.api.core.server_state import iter_log_files

_RTSP_CRED_RE = re.compile(r"(rtsp[s]?://)([^:/@\s]+):([^@/\s]+)@", re.IGNORECASE)
_PASSWORD_ASSIGN_RE = re.compile(r"(password\s*[=:]\s*)([^\s,&;\"']+)", re.IGNORECASE)
_LOG_SESSION_RE = re.compile(r"^(\d{8}_\d{6}(?:_\d+)?)_evileye_main\.log$")
_HEURISTIC_MAX_DELTA_SEC = 120.0


def _logs_dir() -> Path:
    return Path("logs")


def allocate_log_session_id(*, logs_dir: Optional[Path] = None) -> str:
    """Allocate a unique log session prefix (YYYYMMDD_HHMMSS[+_N])."""
    base = datetime.now().strftime("%Y%m%d_%H%M%S")
    root = logs_dir if logs_dir is not None else _logs_dir()
    candidate = base
    suffix = 2
    while (root / f"{candidate}_evileye_main.log").exists():
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def _files_for_session(session_id: str, *, logs_dir: Optional[Path] = None) -> dict[str, Optional[str]]:
    root = logs_dir if logs_dir is not None else _logs_dir()
    out: dict[str, Optional[str]] = {"main": None, "errors": None, "performance": None}
    for kind in ("main", "errors", "performance"):
        name = f"{session_id}_evileye_{kind}.log"
        if (root / name).is_file():
            out[kind] = name
    return out


def _parse_log_session_ts(session_id: str) -> Optional[float]:
    """Parse leading YYYYMMDD_HHMMSS from a log session id into unix timestamp."""
    core = session_id.split("_")
    if len(core) < 2:
        return None
    stamp = f"{core[0]}_{core[1]}"
    try:
        return datetime.strptime(stamp, "%Y%m%d_%H%M%S").timestamp()
    except ValueError:
        return None


def resolve_run_log_files(
        record: dict[str, Any],
        *,
        logs_dir: Optional[Path] = None,
        max_delta_sec: float = _HEURISTIC_MAX_DELTA_SEC,
) -> dict[str, Any]:
    """
    Resolve log files for a runtime record.

    Returns:
      log_session_id, log_files {main, errors, performance}, log_match exact|heuristic|none
    """
    root = logs_dir if logs_dir is not None else _logs_dir()
    empty_files: dict[str, Optional[str]] = {"main": None, "errors": None, "performance": None}
    stored = (record.get("log_session_id") or "").strip() or None
    if stored:
        files = _files_for_session(stored, logs_dir=root)
        # Prefer known main name for deep-links even if file not created yet.
        if files["main"] is None:
            files = {
                **files,
                "main": f"{stored}_evileye_main.log",
            }
        return {
            "log_session_id": stored,
            "log_files": files,
            "log_match": "exact",
        }

    started_at = record.get("started_at")
    if started_at is None:
        return {"log_session_id": None, "log_files": empty_files, "log_match": "none"}

    try:
        target_ts = float(started_at)
    except (TypeError, ValueError):
        return {"log_session_id": None, "log_files": empty_files, "log_match": "none"}

    if not root.exists():
        return {"log_session_id": None, "log_files": empty_files, "log_match": "none"}

    best_sid: Optional[str] = None
    best_delta = float("inf")
    for path in root.glob("*_evileye_main.log"):
        m = _LOG_SESSION_RE.match(path.name)
        if not m:
            continue
        sid = m.group(1)
        ts = _parse_log_session_ts(sid)
        if ts is None:
            continue
        delta = abs(ts - target_ts)
        if delta <= max_delta_sec and delta < best_delta:
            best_delta = delta
            best_sid = sid

    if not best_sid:
        return {"log_session_id": None, "log_files": empty_files, "log_match": "none"}

    return {
        "log_session_id": best_sid,
        "log_files": _files_for_session(best_sid, logs_dir=root),
        "log_match": "heuristic",
    }


def redact_secrets(text: str) -> str:
    if not text:
        return text
    out = _RTSP_CRED_RE.sub(r"\1***:***@", text)
    out = _PASSWORD_ASSIGN_RE.sub(r"\1***", out)
    return out


def list_log_files(*, limit: int = 50) -> dict:
    files = []
    for path in iter_log_files():
        try:
            stat = path.stat()
        except Exception:
            continue
        files.append(
            {
                "name": path.name,
                "updated_at": stat.st_mtime,
                "size_bytes": stat.st_size,
            }
        )
        if len(files) >= limit:
            break
    return {"available": bool(files), "files": files}


def read_log_file(name: str, *, tail: int | None = None) -> dict:
    safe_name = Path(name).name
    if safe_name != name or ".." in name:
        raise ValueError("Invalid log file name")
    path = None
    for candidate in iter_log_files():
        if candidate.name == safe_name:
            path = candidate
            break
    if path is None or not path.exists():
        raise FileNotFoundError(safe_name)
    text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    if tail is not None and tail > 0:
        text = text[-tail:]
    redacted = [redact_secrets(line) for line in text]
    return {
        "name": safe_name,
        "updated_at": path.stat().st_mtime,
        "size_bytes": path.stat().st_size,
        "content": "\n".join(redacted),
        "lines": redacted,
    }


def read_log_tail_from_offset(name: str, *, offset: int = 0, max_bytes: int = 256_000) -> dict:
    """Read new bytes from offset (SSE-friendly). Returns next_offset and appended text."""
    safe_name = Path(name).name
    if safe_name != name or ".." in name:
        raise ValueError("Invalid log file name")
    path = None
    for candidate in iter_log_files():
        if candidate.name == safe_name:
            path = candidate
            break
    if path is None or not path.exists():
        raise FileNotFoundError(safe_name)
    size = path.stat().st_size
    start = max(0, int(offset or 0))
    if start > size:
        start = 0
    to_read = min(max(0, size - start), max_bytes)
    chunk = ""
    if to_read > 0:
        with path.open("rb") as fh:
            fh.seek(start)
            raw = fh.read(to_read)
        chunk = redact_secrets(raw.decode("utf-8", errors="ignore"))
    return {
        "name": safe_name,
        "updated_at": path.stat().st_mtime,
        "size_bytes": size,
        "offset": start,
        "next_offset": start + to_read,
        "chunk": chunk,
        "truncated": size - start > max_bytes,
    }
