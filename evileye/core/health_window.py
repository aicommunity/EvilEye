"""Sliding-window event counters for health signals.

A cumulative counter answers "how many times did this ever happen", which stays non-zero
forever after a short overload. Health flags need "is it happening now", so they are
derived from events inside a recent window while the cumulative total is kept for metrics.
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque

DEGRADED_WINDOW_ENV = "EVILEYE_DEGRADED_WINDOW_SEC"
DEFAULT_DEGRADED_WINDOW_SEC = 60.0
_MAX_TRACKED_EVENTS = 4096


def degraded_window_seconds() -> float:
    """Window used to decide whether a transient problem is still "current"."""
    raw = os.environ.get(DEGRADED_WINDOW_ENV)
    if raw is None:
        return DEFAULT_DEGRADED_WINDOW_SEC
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return DEFAULT_DEGRADED_WINDOW_SEC
    return value if value > 0 else DEFAULT_DEGRADED_WINDOW_SEC


class RollingEventCounter:
    """Counts events; ``recent()`` only covers the last ``window_sec`` seconds."""

    def __init__(self, window_sec: float | None = None, clock=time.monotonic):
        self._window_override = window_sec
        self._clock = clock
        self._events: deque[float] = deque(maxlen=_MAX_TRACKED_EVENTS)
        self._lock = threading.Lock()
        self.total = 0

    @property
    def window_sec(self) -> float:
        if self._window_override is not None:
            return float(self._window_override)
        return degraded_window_seconds()

    def record(self, count: int = 1) -> None:
        now = self._clock()
        with self._lock:
            self.total += count
            for _ in range(min(count, _MAX_TRACKED_EVENTS)):
                self._events.append(now)

    def recent(self) -> int:
        """Events inside the window."""
        horizon = self._clock() - self.window_sec
        with self._lock:
            while self._events and self._events[0] < horizon:
                self._events.popleft()
            return len(self._events)

    def active(self) -> bool:
        return self.recent() > 0

    def reset(self) -> None:
        with self._lock:
            self._events.clear()
            self.total = 0
