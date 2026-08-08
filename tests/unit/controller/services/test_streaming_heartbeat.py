"""StreamingService heartbeat vs full-rate publish policy."""

import os

from evileye.controller.services.streaming_service import StreamingService


class _AliveIdleServer:
    def is_alive(self):
        return True

    def has_preview_demand(self, pipeline_key):
        return False

    def get_preview_demand_level(self, pipeline_key):
        return "idle"


def test_should_publish_heartbeat_one_fps_when_env_set():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_AliveIdleServer())
    service._get_consumer_state = lambda _key: (False, False, True, False)  # type: ignore[method-assign]
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["key"] = key
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    old = os.environ.get("EVILEYE_PREVIEW_HEARTBEAT_FPS")
    os.environ["EVILEYE_PREVIEW_HEARTBEAT_FPS"] = "1"
    try:
        assert service._should_publish("7:0") is True
        assert seen["fps_override"] == 1.0
    finally:
        if old is None:
            os.environ.pop("EVILEYE_PREVIEW_HEARTBEAT_FPS", None)
        else:
            os.environ["EVILEYE_PREVIEW_HEARTBEAT_FPS"] = old


def test_should_publish_full_fps_with_stream_demand():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0)

    class _StreamDemand:
        def is_alive(self):
            return True

        def has_preview_demand(self, pipeline_key):
            return True

        def get_preview_demand_level(self, pipeline_key):
            return "stream"

    service._server_process_manager = _StreamDemand()
    service._get_consumer_state = lambda _key: (False, True, True, False)  # type: ignore[method-assign]
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] == 5.0


def test_has_consumers_false_without_server_or_demand():
    service = StreamingService()

    class _Dead:
        def is_alive(self):
            return False

        def has_preview_demand(self, pipeline_key):
            return False

        def get_preview_demand_level(self, pipeline_key):
            return "idle"

    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_Dead())
    assert service.has_consumers(0) is False
