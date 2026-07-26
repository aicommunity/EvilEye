from __future__ import annotations

import os
import threading
import time
from typing import Callable, Optional

_RESTART_CALLBACK: Optional[Callable[[], None]] = None


class MpCudaStartupHealth:
    """Track fatal CUDA OOM during startup and request a full process restart."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started_at = time.monotonic()
        self._window_sec = self._env_float("EVILEYE_CUDA_OOM_RESTART_WINDOW_SEC", 120.0)
        self._threshold = self._env_float("EVILEYE_CUDA_OOM_RESTART_RATIO", 0.5)
        self._expected_workers = 0
        self._failed_workers = 0
        self._restart_requested = False

    @staticmethod
    def _env_float(name: str, default: float) -> float:
        try:
            return float(os.getenv(name, str(default)) or default)
        except (TypeError, ValueError):
            return default

    @property
    def restart_callback(self) -> Optional[Callable[[], None]]:
        return _RESTART_CALLBACK

    def set_restart_callback(self, callback: Optional[Callable[[], None]]) -> None:
        global _RESTART_CALLBACK
        _RESTART_CALLBACK = callback

    def register_expected_workers(self, count: int) -> None:
        if count <= 0:
            return
        with self._lock:
            self._expected_workers += int(count)

    def record_fatal_oom(self) -> bool:
        """Record a fatal CUDA OOM worker exit. Returns True if restart was triggered."""
        with self._lock:
            self._failed_workers += 1
            if self._restart_requested:
                return True
            if time.monotonic() - self._started_at > self._window_sec:
                return False
            expected = self._expected_workers
            if expected <= 0:
                return False
            if self._failed_workers / expected <= self._threshold:
                return False
            self._restart_requested = True
            return True


_HEALTH: Optional[MpCudaStartupHealth] = None
_HEALTH_LOCK = threading.Lock()


def get_mp_cuda_startup_health() -> MpCudaStartupHealth:
    global _HEALTH
    with _HEALTH_LOCK:
        if _HEALTH is None:
            _HEALTH = MpCudaStartupHealth()
        return _HEALTH
