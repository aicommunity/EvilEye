"""StreamingService heartbeat vs full-rate publish policy."""

from evileye.controller.services.streaming_service import StreamingService


def test_should_publish_heartbeat_one_fps_when_server_alive():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0)
    service._get_consumer_state = lambda _key: (False, False, True, False)  # type: ignore[method-assign]
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["key"] = key
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] == 1.0


def test_should_publish_full_fps_with_demand():
    service = StreamingService()
    service.configure(pipeline_id="7", publish_fps=5.0)
    service._get_consumer_state = lambda _key: (False, True, True, False)  # type: ignore[method-assign]
    seen = {}

    def _throttle(key, *, fps_override=None):
        seen["fps_override"] = fps_override
        return True

    service._throttle_ok = _throttle  # type: ignore[method-assign]
    assert service._should_publish("7:0") is True
    assert seen["fps_override"] is None


def test_has_consumers_false_without_server_or_demand():
    service = StreamingService()

    class _Dead:
        def is_alive(self):
            return False

        def has_preview_demand(self, pipeline_key):
            return False

    service.configure(pipeline_id="7", publish_fps=5.0, server_process_manager=_Dead())
    assert service.has_consumers(0) is False
