"""Thread-safe singleflight: one in-flight call per key, waiters share the result."""

from __future__ import annotations

import threading
from copy import deepcopy
from typing import Any, Callable, TypeVar

T = TypeVar("T")


class SingleFlight:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._inflight: dict[str, dict[str, Any]] = {}

    def do(self, key: str, fn: Callable[[], T]) -> T:
        with self._lock:
            existing = self._inflight.get(key)
            if existing is not None:
                entry = existing
                leader = False
            else:
                entry = {"event": threading.Event(), "result": None, "error": None}
                self._inflight[key] = entry
                leader = True

        if not leader:
            entry["event"].wait()
            err = entry.get("error")
            if err is not None:
                raise err
            return deepcopy(entry.get("result"))

        try:
            result = fn()
            entry["result"] = result
            return result
        except BaseException as exc:
            entry["error"] = exc
            raise
        finally:
            entry["event"].set()
            with self._lock:
                if self._inflight.get(key) is entry:
                    del self._inflight[key]


_default = SingleFlight()


def singleflight(key: str, fn: Callable[[], T]) -> T:
    return _default.do(key, fn)
