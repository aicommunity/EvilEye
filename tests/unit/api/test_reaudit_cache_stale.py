"""Reaudit R06: require_fresh miss must not drop sticky/stale fallback."""

from __future__ import annotations

from evileye.api.core import playback_cache as pc


def setup_function():
    pc.clear_memory_cache()


def test_sticky_survive_require_fresh_miss():
    pc.remember("cameras", [{"name": "Cam2"}], ttl_sec=None)
    assert pc.recall("cameras", require_fresh=True) is None
    stale = pc.recall("cameras", require_fresh=False)
    assert stale == [{"name": "Cam2"}]


def test_ttl_fresh_then_stale_window():
    pc.remember("segs", {"ok": True}, ttl_sec=60.0)
    assert pc.recall("segs", require_fresh=True) == {"ok": True}
    # Force expiry of fresh while keeping stale window by rewriting entry.
    with pc._memory_lock:
        fresh, stale, val, nbytes = pc._memory_cache["segs"]
        pc._memory_cache["segs"] = (0.0, stale, val, nbytes)
    assert pc.recall("segs", require_fresh=True) is None
    assert pc.recall("segs", require_fresh=False) == {"ok": True}
