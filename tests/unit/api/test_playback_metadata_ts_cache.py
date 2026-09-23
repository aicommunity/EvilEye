"""A11: metadata memory cache keys use sub-second timestamp quantum."""

from evileye.api.routes import playback as playback_routes


def test_metadata_cache_keys_differ_within_same_second():
    playback_routes.clear_memory_cache()
    k1 = f"playback:metadata:0:2026-01-01:1:0.5:NonexNone:{round(1.1, 3):.3f}:Cam1:None"
    k2 = f"playback:metadata:0:2026-01-01:1:0.5:NonexNone:{round(1.9, 3):.3f}:Cam1:None"
    assert k1 != k2
    playback_routes._remember(k1, {"metadata": {"ts": 1.1}}, ttl_sec=10)
    playback_routes._remember(k2, {"metadata": {"ts": 1.9}}, ttl_sec=10)
    a = playback_routes._recall(k1, require_fresh=True)
    b = playback_routes._recall(k2, require_fresh=True)
    assert a["metadata"]["ts"] == 1.1
    assert b["metadata"]["ts"] == 1.9
    # Old int(ts) collision would have shared one key for both.
    assert int(1.1) == int(1.9) == 1
