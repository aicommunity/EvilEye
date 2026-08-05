from __future__ import annotations

from pathlib import Path
import re

from evileye.api.core.server_state import iter_log_files

_RTSP_CRED_RE = re.compile(r"(rtsp[s]?://)([^:/@\s]+):([^@/\s]+)@", re.IGNORECASE)
_PASSWORD_ASSIGN_RE = re.compile(r"(password\s*[=:]\s*)([^\s,&;\"']+)", re.IGNORECASE)


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
