"""Shared helpers for heavy API route timeouts (state / playback)."""

from __future__ import annotations

import os


def env_timeout_sec(name: str, default: float, *, floor: float = 2.0) -> float:
    """Read a positive timeout from env with a minimum floor."""
    try:
        raw = os.getenv(name)
        if raw is None or str(raw).strip() == "":
            value = float(default)
        else:
            value = float(raw)
    except Exception:
        value = float(default)
    return max(float(floor), value)


def playback_route_timeout_sec() -> float:
    return env_timeout_sec("EVILEYE_PLAYBACK_ROUTE_TIMEOUT_SEC", 15.0)


def playback_detections_timeout_sec() -> float:
    """Longer wait for coalesced journal scans (ticks/full day index)."""
    return env_timeout_sec("EVILEYE_PLAYBACK_DETECTIONS_TIMEOUT_SEC", 45.0)


def state_route_timeout_sec() -> float:
    return env_timeout_sec("EVILEYE_STATE_ROUTE_TIMEOUT_SEC", 8.0)
