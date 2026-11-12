import time
from threading import Event, Lock, RLock, Thread
from types import SimpleNamespace
from unittest.mock import Mock

from evileye.capture.constants import CaptureConstants
from evileye.capture.gstreamer_capture_frames import GStreamerCaptureFramesMixin
from evileye.capture.gstreamer_capture_pipeline import GStreamerCapturePipelineMixin
from evileye.capture.video_capture_base import VideoCaptureBase
from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer


def _capture():
    return SimpleNamespace(
        _release_lock=Lock(),
        _teardown_pipeline=Mock(),
        logger=Mock(),
        source_names=["camera-test"],
        is_inited=True,
        is_working=True,
    )


def test_release_uses_shared_pipeline_teardown_and_resets_health():
    capture = _capture()

    VideoCaptureGStreamer.release(capture)

    capture._teardown_pipeline.assert_called_once_with("release", join_main_loop=True)
    assert capture.is_inited is False
    assert capture.is_working is False
    assert capture._release_lock.acquire(blocking=False)
    capture._release_lock.release()


def test_release_waits_for_concurrent_teardown_to_finish():
    capture = _capture()
    capture._release_lock.acquire()
    started = Event()
    finished = Event()

    def release_capture():
        started.set()
        VideoCaptureGStreamer.release(capture)
        finished.set()

    worker = Thread(target=release_capture)
    worker.start()
    try:
        assert started.wait(timeout=1.0)
        assert not finished.wait(timeout=0.05)
        capture._teardown_pipeline.assert_not_called()
    finally:
        capture._release_lock.release()

    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert finished.is_set()
    capture._teardown_pipeline.assert_called_once_with("release", join_main_loop=True)


def test_release_releases_lifecycle_lock_when_teardown_fails():
    capture = _capture()
    capture._teardown_pipeline.side_effect = RuntimeError("teardown failed")

    VideoCaptureGStreamer.release(capture)

    capture.logger.error.assert_called_once()
    assert capture._release_lock.acquire(blocking=False)
    capture._release_lock.release()


def test_set_gst_state_null_bounded_returns_after_timeout_and_marks_abandoned():
    class _Pipeline(GStreamerCapturePipelineMixin):
        pass

    hung = Event()

    class _Element:
        def set_state(self, _state):
            hung.wait(10.0)

        def get_state(self, _timeout):
            hung.wait(10.0)
            return (None, None, None)

    capture = _Pipeline()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture._pipeline_null_abandoned = False

    started = time.monotonic()
    ok = capture._set_gst_state_null_bounded(_Element(), timeout_sec=0.2, label="unit-test")
    elapsed = time.monotonic() - started

    assert ok is False
    assert elapsed < 2.0
    assert capture._pipeline_null_abandoned is True
    hung.set()


def test_reconnect_abandons_stalled_release_and_bumps_generation():
    class _Frames(GStreamerCaptureFramesMixin):
        pass

    capture = _Frames()
    capture.pipeline_lock = RLock()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture.pipeline = object()
    capture.bus = object()
    capture.appsink = object()
    capture.is_inited = True
    capture.is_working = True
    capture._pipeline_generation = 3
    capture._pipeline_null_abandoned = False
    capture._reconnect_release_started_at = time.time()
    capture._last_sample_wall_ts = 1.0
    capture._record_disconnect = Mock()

    capture._abandon_stalled_teardown()

    assert capture._reconnect_release_started_at is None
    assert capture._pipeline_null_abandoned is True
    assert capture._pipeline_generation == 4
    assert capture.pipeline is None
    assert capture.appsink is None
    assert capture.is_working is False
    capture._record_disconnect.assert_called_once()


def test_capture_health_is_not_working_while_teardown_pending():
    class _CaptureForHealth(VideoCaptureBase):
        def default(self):
            pass

        def init_impl(self, **kwargs):
            return True

        def release_impl(self):
            pass

        def reset_impl(self):
            pass

        def get_params_impl(self):
            return {}

        def get_frames_impl(self):
            return []

        def _grab_frames(self):
            pass

        def _retrieve_frames(self):
            pass

    capture = _CaptureForHealth()
    capture.is_working = True
    capture._reconnect_release_started_at = time.time()

    health = capture.get_capture_health()
    assert health["working"] is False
    assert health["teardown_pending_since"] is not None

    capture._reconnect_release_started_at = None
    capture._pipeline_null_abandoned = True
    health = capture.get_capture_health()
    assert health["working"] is False

    capture._pipeline_null_abandoned = False
    health = capture.get_capture_health()
    assert health["working"] is True


def test_recording_queue_pipeline_uses_leaky_downstream():
    class _Pipeline(GStreamerCapturePipelineMixin):
        pass

    capture = _Pipeline()
    capture.source_type = Mock()
    from evileye.capture.video_capture_base import CaptureDeviceType

    capture.source_type = CaptureDeviceType.IpCamera
    capture.source_address = "rtsp://10.245.1.202"
    capture.username = "u"
    capture.password = "p"
    capture._rtsp_protocol = "udp+tcp"
    capture.recording_params = SimpleNamespace(enabled=True, continuous_recording_enabled=True)
    capture.params = {}

    candidates = capture._build_pipeline_candidates()
    assert candidates
    assert "leaky=downstream" in candidates[0]
    assert "leaky=no" not in candidates[0]


def test_restart_script_uses_detach_and_survived_kill_error():
    from pathlib import Path

    text = Path("evileye/deploy_monitor/scripts/restart_evileye.sh").read_text(encoding="utf-8")
    assert "--detach" in text
    assert "survived SIGKILL" in text
    assert 'Child already running after stop (another agent)' not in text
    assert CaptureConstants.RECONNECT_RELEASE_WAIT_SEC > 0
    assert CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC > 0
