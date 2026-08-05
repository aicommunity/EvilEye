"""Tiered preview demand levels (idle / grid / stream)."""

import time

from evileye.controller.services.streaming_service import StreamingService
from evileye.server import ServerProcessManager


class _AliveServer:
    def __init__(self, level: str = "grid"):
        self._level = level

    def is_alive(self):
        return True

    def has_preview_demand(self, pipeline_key):
        return self._level != "idle"

    def get_preview_demand_level(self, pipeline_key):
        return self._level


def test_server_process_manager_level_merge_stream_over_grid():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:0", level="grid")
    mgr.touch_preview_demand("7:0", level="stream")
    assert mgr.get_preview_demand_level("7:0") == "stream"


def test_server_process_manager_grid_does_not_downgrade_stream():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:0", level="stream")
    mgr.touch_preview_demand("7:0", level="grid")
    assert mgr.get_preview_demand_level("7:0") == "stream"


def test_server_process_manager_ttl_expires_to_idle():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:0", touched_at=time.time() - 30, level="grid")
    assert mgr.get_preview_demand_level("7:0", ttl_sec=20.0) == "idle"


def test_should_publish_grid_fps_with_grid_demand():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveServer("grid"))
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] == 2.0


def test_should_publish_stream_fps_with_stream_demand():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveServer("stream"))
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] == 5.0


def test_should_publish_false_when_server_alive_no_demand_default_heartbeat():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveServer("idle"))
    assert service._should_publish("7:0") is False


def test_has_consumers_false_without_demand_or_heartbeat():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveServer("idle"))
    assert service.has_consumers(0) is False
