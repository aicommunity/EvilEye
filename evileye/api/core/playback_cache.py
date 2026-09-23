"""In-process playback response memory cache (LRU + soft byte budget)."""

from __future__ import annotations

import json
import sys
import threading
import time
from copy import deepcopy
from typing import Any

_memory_lock = threading.Lock()
# key -> (fresh_until|None, stale_until, value, nbytes)
_memory_cache: dict[str, tuple[float | None, float, Any, int]] = {}
_MEMORY_CACHE_MAX_KEYS = 256
_MEMORY_CACHE_MAX_BYTES = 64 * 1024 * 1024  # soft budget (A12)
_STALE_GRACE_SEC = 300.0
_STALE_BUDGET_STICKY_SEC = 3600.0
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
    now = time.time()
    if ttl_sec is not None:
        fresh_until: float | None = now + float(ttl_sec)
        stale_until = now + max(float(ttl_sec), _STALE_GRACE_SEC)
    else:
        # Sticky: never fresh for require_fresh; keep as stale fallback (R06).
        fresh_until = None
        stale_until = now + _STALE_BUDGET_STICKY_SEC
    # Copy outside the lock to reduce contention (A12).
    t0 = time.perf_counter()
    stored = deepcopy(value)
    copy_ms = (time.perf_counter() - t0) * 1000.0
    est = _estimate_cache_bytes(stored)
    # Reject single oversized entries instead of pinning forever (R15).
    if est > _MEMORY_CACHE_MAX_BYTES:
        return
    with _memory_lock:
        _copy_ms_total += copy_ms
        _copy_count += 1
        now = time.time()
        expired = [
            k
            for k, (_fresh, stale, _val, _n) in _memory_cache.items()
            if stale <= now
        ]
        for k in expired:
            old = _memory_cache.pop(k, None)
            if old is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - old[3])
        old_entry = _memory_cache.pop(key, None)
        if old_entry is not None:
            _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - old_entry[3])
        _memory_cache[key] = (fresh_until, stale_until, stored, est)
        _memory_cache_bytes_est += est
        while _memory_cache and (
            len(_memory_cache) > _MEMORY_CACHE_MAX_KEYS
            or _memory_cache_bytes_est > _MEMORY_CACHE_MAX_BYTES
        ):
            oldest = next(iter(_memory_cache))
            if oldest == key and len(_memory_cache) == 1:
                # Only entry still over budget — drop it rather than pin forever.
                dropped = _memory_cache.pop(oldest, None)
                if dropped is not None:
                    _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - dropped[3])
                break
            if oldest == key:
                cur = _memory_cache.pop(key)
                _memory_cache[key] = cur
                oldest = next(iter(_memory_cache))
                if oldest == key:
                    break
            evicted = _memory_cache.pop(oldest, None)
            if evicted is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - evicted[3])


def recall(key: str, *, require_fresh: bool = False) -> Any | None:
    global _memory_cache_bytes_est
    with _memory_lock:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        fresh_until, stale_until, cached, nbytes = entry
        now = time.time()
        if require_fresh:
            # Fresh miss must NOT drop stale fallback (R06).
            if fresh_until is None or fresh_until <= now:
                return None
        elif stale_until <= now:
            popped = _memory_cache.pop(key, None)
            if popped is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - popped[3])
            return None
        # LRU touch
        _memory_cache.pop(key, None)
        _memory_cache[key] = (fresh_until, stale_until, cached, nbytes)
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
        for fresh_until, stale_until, _val, _n in _memory_cache.values():
            if fresh_until is None:
                sticky += 1
            elif fresh_until > now:
                fresh += 1
            elif stale_until <= now:
                expired += 1
            else:
                # Past fresh but within stale window.
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
