"""In-process playback response memory cache (LRU + soft byte budget)."""

from __future__ import annotations

import json
import sys
import threading
import time
from copy import deepcopy
from typing import Any

from evileye.api.core.cache_policy import DEFAULT_CACHE_POLICY, CachePolicy

_memory_lock = threading.Lock()
# key -> (fresh_until|None, stale_until, value, nbytes)
_memory_cache: dict[str, tuple[float | None, float, Any, int]] = {}
_policy: CachePolicy = DEFAULT_CACHE_POLICY
_memory_cache_bytes_est = 0
_copy_ms_total = 0.0
_copy_count = 0


def set_cache_policy(policy: CachePolicy | None = None) -> CachePolicy:
    """Replace active policy (tests / diagnostics). None restores default."""
    global _policy
    with _memory_lock:
        _policy = policy or DEFAULT_CACHE_POLICY
        return _policy


def get_cache_policy() -> CachePolicy:
    return _policy


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
    policy = _policy
    fresh_until, stale_until = policy.fresh_and_stale(ttl_sec)
    # F11: estimate before deepcopy to avoid temp RAM spike on oversized reject.
    est_probe = _estimate_cache_bytes(value)
    if est_probe > policy.max_bytes:
        return
    t0 = time.perf_counter()
    stored = deepcopy(value)
    copy_ms = (time.perf_counter() - t0) * 1000.0
    est = _estimate_cache_bytes(stored)
    if est > policy.max_bytes:
        return
    with _memory_lock:
        _copy_ms_total += copy_ms
        _copy_count += 1
        now = float(policy.clock())
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
            len(_memory_cache) > policy.max_keys
            or _memory_cache_bytes_est > policy.max_bytes
        ):
            oldest = next(iter(_memory_cache))
            if oldest == key and len(_memory_cache) == 1:
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
    policy = _policy
    with _memory_lock:
        entry = _memory_cache.get(key)
        if entry is None:
            return None
        fresh_until, stale_until, cached, nbytes = entry
        now = float(policy.clock())
        if require_fresh:
            if fresh_until is None or fresh_until <= now:
                return None
        elif stale_until <= now:
            popped = _memory_cache.pop(key, None)
            if popped is not None:
                _memory_cache_bytes_est = max(0, _memory_cache_bytes_est - popped[3])
            return None
        _memory_cache.pop(key, None)
        _memory_cache[key] = (fresh_until, stale_until, cached, nbytes)
        snapshot = cached
    return deepcopy(snapshot)


def memory_cache_stats(*, extra: dict[str, int | float] | None = None) -> dict[str, int | float]:
    """Observability: in-process playback memory cache size and freshness."""
    policy = _policy
    now = float(policy.clock())
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
        "max_bytes": int(policy.max_bytes),
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
