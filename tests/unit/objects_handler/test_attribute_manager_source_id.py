"""Unit tests for AttributeManager (source_id, track_id) keys."""

from __future__ import annotations

from evileye.objects_handler.attribute_manager import AttributeManager


def test_attribute_keys_isolated_by_source_id():
    mgr = AttributeManager(
        thresholds_conf={"hard_hat": 0.1},
        thresholds_time={"hard_hat": {"min_time_ms": 0, "confirm_time_ms": 0}},
    )
    mgr.update(1, "hard_hat", True, 0.9, now_ts=1.0, dt_ms=33, source_id=0)
    mgr.update(1, "hard_hat", False, 0.0, now_ts=2.0, dt_ms=33, source_id=1)

    s0 = mgr.get_states(1, source_id=0)
    s1 = mgr.get_states(1, source_id=1)
    assert "hard_hat" in s0
    assert "hard_hat" in s1
    assert s0["hard_hat"].total_found_time_ms == 33
    assert s1["hard_hat"].total_found_time_ms == 0
    assert s1["hard_hat"].total_lost_time_ms == 33

    mgr.remove_track(1, source_id=0)
    assert mgr.get_states(1, source_id=0) == {}
    assert "hard_hat" in mgr.get_states(1, source_id=1)
