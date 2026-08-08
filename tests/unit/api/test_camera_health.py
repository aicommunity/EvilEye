"""Unit tests for server_state._camera_health field semantics."""

from evileye.api.core import server_state as ss


def _run(*, state="running", snap_sources=None):
    run = {"id": 1, "state": state}
    if snap_sources is not None:
        run["runtime_snapshot"] = {"sources": snap_sources}
    return run


def test_camera_health_matrix(monkeypatch):
    cases = [
        # snap_working, preview, age, state -> is_working, reconnecting, preview_available
        (True, False, None, "running", True, False, False),
        (True, True, 1.0, "running", True, False, True),
        (False, True, 1.0, "running", False, True, True),
        (False, False, None, "running", False, True, False),
        (None, False, None, "running", True, False, False),
        (None, True, 8.0, "running", False, False, True),
        (None, True, 2.0, "running", True, False, True),
        (True, True, 1.0, "stopped", False, False, False),
    ]

    for snap_working, preview, age, state, exp_working, exp_reconn, exp_preview in cases:
        snap_sources = None
        if snap_working is not None:
            snap_sources = [{"source_ids": [0], "is_working": snap_working}]

        monkeypatch.setattr(ss, "_frame_age_sec", lambda *_a, **_k: age)
        monkeypatch.setattr(ss, "_preview_frame_available", lambda *_a, **_k: preview)

        preview_out, age_out, is_working, reconnecting = ss._camera_health(
            _run(state=state, snap_sources=snap_sources),
            0,
        )
        assert preview_out is exp_preview, (snap_working, preview, age, state)
        assert age_out == age
        assert is_working is exp_working, (snap_working, preview, age, state)
        assert reconnecting is exp_reconn, (snap_working, preview, age, state)


def test_missing_preview_with_live_capture_is_not_reconnecting(monkeypatch):
    monkeypatch.setattr(ss, "_frame_age_sec", lambda *_a, **_k: None)
    monkeypatch.setattr(ss, "_preview_frame_available", lambda *_a, **_k: False)
    preview, _age, is_working, reconnecting = ss._camera_health(
        _run(snap_sources=[{"source_ids": [0], "is_working": True}]),
        0,
    )
    assert preview is False
    assert is_working is True
    assert reconnecting is False
