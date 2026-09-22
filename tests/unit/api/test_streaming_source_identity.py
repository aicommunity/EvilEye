"""Per-source JPEG lookup must not fall back to run-level frames."""

from __future__ import annotations

from types import SimpleNamespace

from evileye.api.routes import streaming as streaming_routes


class _FakeBroker:
    def __init__(self, frames: dict[str, bytes]):
        self.frames = frames

    def latest_jpeg(self, key: str):
        return self.frames.get(key)


def test_load_latest_frame_source_miss_does_not_use_run_level(monkeypatch):
    broker = _FakeBroker({"20": b"run-level", "20:1": b"cam1"})
    monkeypatch.setattr(streaming_routes, "get_frame_broker", lambda: broker)
    run_info = {"id": 20}

    assert streaming_routes._load_latest_frame(run_info, source_id=1) == b"cam1"
    assert streaming_routes._load_latest_frame(run_info, source_id=2) is None
    assert streaming_routes._load_latest_frame(run_info, source_id=None) == b"run-level"


def test_frame_relay_health_fields():
    from evileye.controller.services.streaming_service import FrameRelayClient

    client = FrameRelayClient("https://127.0.0.1:8181/api/v1", token="tok")
    try:
        health = client.health()
        assert "relay_fail_streak" in health
        assert "relay_last_ok_age_sec" in health
    finally:
        client.close()
