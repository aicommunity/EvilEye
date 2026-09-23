"""In-process playback response memory cache (LRU + soft byte budget)."""

from __future__ import annotations

import json
import sys
import threading
import time
from copy import deepcopy
from typing import Any

_memory_lock = threading.Lock()
# key -> (expires_at_or_None, value). expires_at None = sticky timeout fallback only.
_memory_cache: dict[str, tuple[float | None, Any]] = {}
_MEMORY_CACHE_MAX_KEYS = 256
_MEMORY_CACHE_MAX_BYTES = 64 * 1024 * 1024  # soft budget (A12)
_memory_cache_bytes_est = 0
_copy_ms_total = 0.0
_copy_count = 0


def _estimate_cache_bytes(value: Any) -> int:
    """Soft size estimate for byte-budget eviction (JSON length preferred)."""
    try:
        return len(json.dumps(value, default=str))
    except Exception:
        try:
            return int(sys.getsizeof(value))
        except Exception:
            return 0


def remember(key: str, value: Any, *, ttl_sec: float | None = None) -> None:
    global _memory_cache_bytes_est, _copy_ms_total, _copy_count
    expires_at = (time.time() + float(ttl_sec)) if ttl_sec is not None else None
    # Copy outside the lock to reduce contention (A12).
    t0 = time.perf_counter()
    stored = deepcopy(value)
    copy_ms = (time.perf_counter() - t0) * 1000.0
    est = _estimate_cache_bytes(stored)
    with _memory_lock:
        _copy_ms_total += copy_ms
        _copy_count += 1
        now = time.time()
        expired = [k for k, (exp, _) in _memory_cache.items() if exp is not None and exp <= now]
        for k in expired:
            old = _memory_cache.pop(k, None)
            if old is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - _estimate_cache_bytes(old[1]))
        old_entry = _memory_cache.pop(key, None)
        if old_entry is not None:
            _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - _estimate_cache_bytes(old_entry[1]))
        _memory_cache[key] = (expires_at, stored)
        _memory_cache_bytes_est += est
        while _memory_cache and (
            len(_memory_cache) > _MEMORY_CACHE_MAX_KEYS or _memory_cache_bytes_est > _MEMORY_CACHE_MAX_BYTES
        ):
            oldest = next(iter(_memory_cache))
            if oldest == key and len(_memory_cache) == 1:
                break
            if oldest == key:
                cur = _memory_cache.pop(key)
                _memory_cache[key] = cur
                oldest = next(iter(_memory_cache))
                if oldest == key:
                    break
            evicted = _memory_cache.pop(oldest, None)
            if evicted is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - _estimate_cache_bytes(evicted[1]))


def recall(key: str, *, require_fresh: bool = False) -> Any | None:
    global _memory_cache_bytes_est
    with _memory_lock:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        expires_at, cached = entry
        if require_fresh:
            if expires_at is None or expires_at <= time.time():
                popped = _memory_cache.pop(key, None)
                if popped is not None:
                    _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - _estimate_cache_bytes(popped[1]))
                return None
        _memory_cache.pop(key, None)
        _memory_cache[key] = (expires_at, cached)
        snapshot = cached
    return deepcopy(snapshot)


def memory_cache_stats(*, extra: dict[str, int | float] | None = None) -> dict[str, int | float]:
    """Observability: in-process playback memory cache size and freshness."""
    now = time.time()
    with _memory_lock:
        keys = len(_memory_cache)
        fresh = 0
        expired = 0
        sticky = 0
        for expires_at, _ in _memory_cache.values():
            if expires_at is None:
                sticky += 1
            elif expires_at > now:
                fresh += 1
            else:
                expired += 1
        bytes_est = int(_memory_cache_bytes_est)
        copy_ms = float(_copy_ms_total)
        copies = int(_copy_count)
    out: dict[str, int | float] = {
        "keys": keys,
        "fresh": fresh,
        "expired": expired,
        "sticky": sticky,
        "bytes_est": bytes_est,
        "max_bytes": int(_MEMORY_CACHE_MAX_BYTES),
        "copy_ms": round(copy_ms, 3),
        "copy_count": copies,
    }
    if extra:
        out.update(extra)
    return out


def clear_memory_cache() -> int:
    """Clear in-process playback memory cache (diagnostics / cold-server simulation)."""
    global _memory_cache_bytes_est
    with _memory_lock:
        cleared = len(_memory_cache)
        _memory_cache.clear()
        _memory_cache_bytes_est = 0
    return cleared
