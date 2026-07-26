from __future__ import annotations

import datetime
from typing import Any


def server_timezone() -> datetime.tzinfo:
    return datetime.datetime.now().astimezone().tzinfo


def parse_journal_timestamp(value: Any) -> datetime.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return None
        try:
            return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def format_journal_timestamp(value: Any) -> str:
    """Naive timestamps from JSON/DB are treated as server-local and annotated with offset."""
    dt = parse_journal_timestamp(value)
    if dt is None:
        return str(value or "")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=server_timezone())
    return dt.isoformat(timespec="seconds")


def normalize_row_times(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    for key in ("time", "time_lost"):
        val = out.get(key)
        if val:
            out[key] = format_journal_timestamp(val)
    return out
