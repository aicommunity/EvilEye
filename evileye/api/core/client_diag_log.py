"""Append client diagnostic events to daily JSONL files under logs/."""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def _logs_dir() -> Path:
    return Path("logs")


def client_diag_path(*, logs_dir: Path | None = None, day: datetime | None = None) -> Path:
    root = logs_dir if logs_dir is not None else _logs_dir()
    when = day or datetime.now(timezone.utc).astimezone()
    return root / f"client_diag_{when.strftime('%Y%m%d')}.log"


def append_client_diag_events(
    *,
    user: str,
    session_id: str,
    events: list[dict[str, Any]],
    ua: str | None = None,
    page: str | None = None,
    logs_dir: Path | None = None,
) -> int:
    """Write one JSON line per event. Returns number of lines written."""
    if not events:
        return 0
    path = client_diag_path(logs_dir=logs_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    server_ts = time.time()
    written = 0
    with _LOCK:
        with path.open("a", encoding="utf-8") as fh:
            for ev in events:
                if not isinstance(ev, dict):
                    continue
                row = {
                    "ts": server_ts,
                    "user": user,
                    "session_id": session_id,
                    "ua": ua,
                    "page": page,
                    "event": ev,
                }
                fh.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                written += 1
    return written
