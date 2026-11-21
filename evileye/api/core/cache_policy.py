"""Playback memory-cache policy knobs (T19) with injectable clock."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class CachePolicy:
    max_keys: int = 256
    max_bytes: int = 64 * 1024 * 1024
    stale_grace_sec: float = 300.0
    sticky_stale_budget_sec: float = 3600.0
    clock: Callable[[], float] = time.time

    def fresh_and_stale(self, ttl_sec: float | None) -> tuple[float | None, float]:
        now = float(self.clock())
        if ttl_sec is not None:
            fresh = now + float(ttl_sec)
            stale = now + max(float(ttl_sec), self.stale_grace_sec)
            return fresh, stale
        return None, now + self.sticky_stale_budget_sec


DEFAULT_CACHE_POLICY = CachePolicy()
