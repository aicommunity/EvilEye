"""Convert object/event timestamps to naive local datetime."""
from __future__ import annotations

import datetime
from typing import Any


def datetime_from_ts(value: Any) -> datetime.datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime.datetime):
        return value
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return datetime.datetime.combine(value, datetime.time.min)
    if isinstance(value, (int, float)):
        try:
            return datetime.datetime.fromtimestamp(float(value))
        except (OSError, OverflowError, ValueError):
            return None
    if isinstance(value, str):
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1]
        try:
            return datetime.datetime.fromisoformat(text)
        except ValueError:
            return None
    return None


def obj_found_datetime(obj: Any) -> datetime.datetime:
    dt = datetime_from_ts(getattr(obj, "time_stamp", None))
    if dt is None:
        dt = datetime_from_ts(getattr(obj, "time_detected", None))
    return dt if dt is not None else datetime.datetime.now()


def obj_lost_datetime(obj: Any) -> datetime.datetime:
    dt = datetime_from_ts(getattr(obj, "time_lost", None))
    if dt is None:
        dt = datetime_from_ts(getattr(obj, "time_stamp", None))
    return dt if dt is not None else datetime.datetime.now()


def require_datetime(value: Any) -> datetime.datetime:
    dt = datetime_from_ts(value)
    return dt if dt is not None else datetime.datetime.now()


def date_folder_from_ts(value: Any) -> str:
    return require_datetime(value).strftime("%Y-%m-%d")
