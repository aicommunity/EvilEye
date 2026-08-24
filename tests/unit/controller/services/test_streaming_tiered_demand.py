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


def test_server_process_manager_force_downgrade_stream_to_grid():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:0", level="stream")
    mgr.touch_preview_demand("7:0", level="grid", force=True)
    assert mgr.get_preview_demand_level("7:0") == "grid"


def test_server_process_manager_ttl_expires_to_idle():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:0", touched_at=time.time() - 30, level="grid")
    assert mgr.get_preview_demand_level("7:0", ttl_sec=20.0) == "idle"


def test_full_demand_does_not_inherit_root_live_demand():
    """Live touches root run id; that must not enable split full-frame encode."""
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7", level="grid")
    mgr.touch_preview_demand("7:1", level="grid")
    assert mgr.get_preview_demand_level("7") == "grid"
    assert mgr.get_preview_demand_level("7:1") == "grid"
    assert mgr.get_preview_demand_level("7:full:1") == "idle"


def test_explicit_full_demand_is_honored():
    mgr = ServerProcessManager()
    mgr.touch_preview_demand("7:full:1", level="stream")
    assert mgr.get_preview_demand_level("7:full:1") == "stream"


def test_submit_full_frame_ignores_crop_sibling_demand():
    service = StreamingService()

    class _Mgr:
        def is_alive(self):
            return True

        def has_preview_demand(self, pipeline_key):
            # Crop demand only — no explicit :full: key.
            return pipeline_key in {"7", "7:1", "7:2"}

        def get_preview_demand_level(self, pipeline_key):
            if ":full:" in pipeline_key:
                return "idle"
            return "grid"

    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_Mgr())
    import numpy as np

    image = np.zeros((16, 16, 3), dtype=np.uint8)
    assert service.submit_full_frame(image, primary_source_id=1, source_ids=[1, 2]) is False


def test_should_publish_grid_fps_with_grid_demand():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveServer("grid"))
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] == 5.0


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


def test_relay_without_server_process_publishes_at_fps():
    """OS-service Web UI: no ServerProcessManager, only HTTPS frame relay."""
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=None)
    service.set_frame_relay("https://127.0.0.1:8181/api/v1", "token")
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    try:
        assert service.has_consumers(0) is True
        assert service._should_publish("7:0") is True
        assert seen["fps_override"] == 5.0
    finally:
        service.set_frame_relay(None)
