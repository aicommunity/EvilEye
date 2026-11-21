"""GStreamer PTS helpers for capture frames (no Gst import)."""
from __future__ import annotations

GST_CLOCK_TIME_NONE = 0xFFFFFFFFFFFFFFFF


def valid_pts_ns(pts_ns: int | float | None) -> bool:
    if pts_ns is None:
        return False
    try:
        value = int(pts_ns)
    except (TypeError, ValueError):
        return False
    return 0 <= value < GST_CLOCK_TIME_NONE


def media_pts_sec(pts_ns: int, first_pts_ns: int) -> float:
    return (int(pts_ns) - int(first_pts_ns)) / 1_000_000_000.0
