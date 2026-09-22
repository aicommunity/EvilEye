"""Allowlist for forced client-side diagnostics upload."""

from __future__ import annotations

import os
from functools import lru_cache

DEFAULT_DEBUG_USERS = (
    "onmatsko@gmail.com",
    "e2e-playback@example.com",
    "playback-test@example.com",
    "admin",
)

_SUBSTRING_HINTS = ("omatsko", "onmatsko")


def _normalize(value: str | None) -> str:
    return (value or "").strip().lower()


@lru_cache(maxsize=1)
def _allowlist() -> frozenset[str]:
    names = {_normalize(u) for u in DEFAULT_DEBUG_USERS if u}
    extra = os.getenv("EVILEYE_CLIENT_DEBUG_USERS") or ""
    for part in extra.split(","):
        n = _normalize(part)
        if n:
            names.add(n)
    return frozenset(names)


def clear_client_debug_cache() -> None:
    """Test helper: drop cached allowlist after env changes."""
    _allowlist.cache_clear()


def user_client_debug_enabled(username: str | None) -> bool:
    """Return True when client telemetry must auto-enable for this session user."""
    name = _normalize(username)
    if not name:
        return False
    if name in _allowlist():
        return True
    return any(hint in name for hint in _SUBSTRING_HINTS)
