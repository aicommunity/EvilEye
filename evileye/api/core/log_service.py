from __future__ import annotations

from pathlib import Path

from evileye.api.core.server_state import iter_log_files


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
    return {
        "name": safe_name,
        "updated_at": path.stat().st_mtime,
        "size_bytes": path.stat().st_size,
        "content": "\n".join(text),
        "lines": text,
    }
