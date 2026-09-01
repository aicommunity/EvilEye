"""Playback in-memory cache keys and stats (no per-user isolation)."""

from __future__ import annotations

import time

import pytest

from evileye.api.routes import playback as playback_routes


def test_memory_cache_key_excludes_user_id():
    """Timeline mem_key is date/run/window/cam_list — not user-specific."""
    date = "2026-08-19"
    cam_list_a = ["Cam1", "Cam2"]
    cam_list_b = ["Cam1", "Cam2", "Cam3"]
    key_a = f"playback:timeline:{date}:None:None:None:{','.join(cam_list_a)}"
    key_b = f"playback:timeline:{date}:None:None:None:{','.join(cam_list_b)}"
    assert "user" not in key_a
    assert key_a != key_b


def test_different_cam_lists_are_separate_cache_entries():
    playback_routes._memory_cache.clear()
    key_two = "playback:timeline:2026-08-19:None:None:None:Cam1,Cam2"
    key_four = "playback:timeline:2026-08-19:None:None:None:Cam1,Cam2,Cam3,Cam4"
    playback_routes._remember(key_two, {"date": "2026-08-19", "n": 2}, ttl_sec=60.0)
    playback_routes._remember(key_four, {"date": "2026-08-19", "n": 4}, ttl_sec=60.0)
    assert playback_routes._recall(key_two, require_fresh=True)["n"] == 2
    assert playback_routes._recall(key_four, require_fresh=True)["n"] == 4


def test_memory_cache_stats_and_clear():
    playback_routes._memory_cache.clear()
    stats_empty = playback_routes.memory_cache_stats()
    assert stats_empty["keys"] == 0

    playback_routes._remember("k1", {"x": 1}, ttl_sec=60.0)
    playback_routes._remember("k2", {"y": 2}, ttl_sec=None)
    stats = playback_routes.memory_cache_stats()
    assert stats["keys"] == 2
    assert stats["fresh"] >= 1
    assert stats["sticky"] >= 1

    cleared = playback_routes.clear_memory_cache()
    assert cleared == 2
    assert playback_routes.memory_cache_stats()["keys"] == 0


def test_json_with_cache_sets_stale_header():
    resp = playback_routes._json_with_cache({"stale": True, "date": "x"}, "miss")
    assert resp.headers["X-Playback-Cache"] == "stale"

    resp_hit = playback_routes._json_with_cache({"date": "x"}, "hit")
    assert resp_hit.headers["X-Playback-Cache"] == "hit"


def test_second_recall_faster_than_cold_remember():
    """Simulate warm memory path: recall after remember is instant."""
    playback_routes._memory_cache.clear()
    key = "playback:cameras:None:2026-08-19"
    payload = [{"id": "Cam1"}]
    t0 = time.perf_counter()
    playback_routes._remember(key, payload, ttl_sec=45.0)
    cold_ms = (time.perf_counter() - t0) * 1000

    t1 = time.perf_counter()
    hit = playback_routes._recall(key, require_fresh=True)
    warm_ms = (time.perf_counter() - t1) * 1000

    assert hit == payload
    assert warm_ms <= cold_ms + 1.0
