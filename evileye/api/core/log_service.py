from __future__ import annotations

from pathlib import Path
from typing import Any

from evileye.api.core.server_state import iter_log_files


def load_runtime_logs(*, lines: int, limit: int = 5) -> dict[str, Any]:
    files = []
    for path in iter_log_files():
        try:
            text = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception:
            continue
        files.append(
            {
                "name": path.name,
                "updated_at": path.stat().st_mtime,
                "lines": text[-lines:],
            }
        )
        if len(files) >= limit:
            break
    return {"available": bool(files), "files": files}
