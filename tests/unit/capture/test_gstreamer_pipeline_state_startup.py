from types import SimpleNamespace

import pytest

import evileye.capture.gstreamer_capture_pipeline as pipeline_module
from evileye.capture.gstreamer_capture_pipeline import GStreamerCapturePipelineMixin


class _Pipeline:
    def __init__(self, set_state_result, get_state_result=None):
        self.set_state_result = set_state_result
        self.get_state_result = get_state_result
        self.get_state_timeouts = []

    def set_state(self, state):
        assert state == "playing"
        return self.set_state_result

    def get_state(self, timeout):
        self.get_state_timeouts.append(timeout)
        return self.get_state_result


@pytest.fixture
def fake_gst(monkeypatch):
    state_change = SimpleNamespace(FAILURE="failure", ASYNC="async", SUCCESS="success")
    gst = SimpleNamespace(
        State=SimpleNamespace(PLAYING="playing"),
        StateChangeReturn=state_change,
        SECOND=1_000_000_000,
    )
    monkeypatch.setattr(pipeline_module, "Gst", gst)
    return gst


def _capture(pipeline):
    return SimpleNamespace(pipeline=pipeline)


def test_live_pipeline_start_does_not_block_on_rtsp_state(fake_gst):
    pipeline = _Pipeline(fake_gst.StateChangeReturn.ASYNC)

    GStreamerCapturePipelineMixin._set_pipeline_playing(
        _capture(pipeline), wait_for_async=False
    )

    assert pipeline.get_state_timeouts == []


def test_finite_pipeline_state_wait_has_a_ten_second_bound(fake_gst):
    pipeline = _Pipeline(
        fake_gst.StateChangeReturn.ASYNC,
        (fake_gst.StateChangeReturn.SUCCESS, "playing", "void-pending"),
    )

    GStreamerCapturePipelineMixin._set_pipeline_playing(
        _capture(pipeline), wait_for_async=True
    )

    assert pipeline.get_state_timeouts == [10 * fake_gst.SECOND]


def test_finite_pipeline_start_timeout_is_reported(fake_gst):
    pipeline = _Pipeline(
        fake_gst.StateChangeReturn.ASYNC,
        (fake_gst.StateChangeReturn.ASYNC, "paused", "playing"),
    )

    with pytest.raises(TimeoutError, match="exceeded 10 seconds"):
        GStreamerCapturePipelineMixin._set_pipeline_playing(
            _capture(pipeline), wait_for_async=True
        )


def test_pipeline_state_failure_is_reported_without_wait(fake_gst):
    pipeline = _Pipeline(fake_gst.StateChangeReturn.FAILURE)

    with pytest.raises(RuntimeError, match="Failed to start"):
        GStreamerCapturePipelineMixin._set_pipeline_playing(
            _capture(pipeline), wait_for_async=False
        )

    assert pipeline.get_state_timeouts == []


def test_rtsp_uses_direct_gio_proxy_resolver_by_default(monkeypatch):
    import evileye.capture.video_capture_gstreamer as capture_module

    monkeypatch.delenv("GIO_USE_PROXY_RESOLVER", raising=False)
    capture_module._configure_direct_rtsp_proxy_resolver()

    assert __import__("os").environ["GIO_USE_PROXY_RESOLVER"] == "dummy"


def test_rtsp_preserves_an_explicit_gio_proxy_resolver(monkeypatch):
    import evileye.capture.video_capture_gstreamer as capture_module

    monkeypatch.setenv("GIO_USE_PROXY_RESOLVER", "custom")
    capture_module._configure_direct_rtsp_proxy_resolver()

    assert __import__("os").environ["GIO_USE_PROXY_RESOLVER"] == "custom"
