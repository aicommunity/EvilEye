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

    capture._teardown_pipeline.assert_called_once_with(
        "release", join_main_loop=True, expected_generation=0
    )
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
    capture._teardown_pipeline.assert_called_once_with(
        "release", join_main_loop=True, expected_generation=0
    )


def test_release_releases_lifecycle_lock_when_teardown_fails():
    capture = _capture()
    capture._teardown_pipeline.side_effect = RuntimeError("teardown failed")

    VideoCaptureGStreamer.release(capture)

    capture.logger.error.assert_called_once()
    assert capture._release_lock.acquire(blocking=False)
    capture._release_lock.release()


def test_release_drops_lifecycle_lock_before_native_teardown():
    capture = _capture()
    started = Event()

    def slow_teardown(*_args, **_kwargs):
        started.set()
        time.sleep(0.3)

    capture._teardown_pipeline = slow_teardown
    worker = Thread(target=VideoCaptureGStreamer.release, args=(capture,))
    worker.start()
    assert started.wait(timeout=1.0)
    assert capture._release_lock.acquire(timeout=0.1)
    capture._release_lock.release()
    worker.join(timeout=1.0)
    assert not worker.is_alive()


def test_reconnect_skips_an_abandoned_release_event():
    from evileye.capture.video_capture_base import CaptureDeviceType

    class _Stop:
        def is_set(self):
            return False

        def wait(self, _timeout):
            return True

    class _Frames(GStreamerCaptureFramesMixin):
        pass

    capture = _Frames()
    capture.run_flag = True
    capture.stop_event = _Stop()
    capture._reconnecting = False
    capture.is_inited = False
    capture.is_working = False
    capture.source_type = CaptureDeviceType.IpCamera
    capture.source_names = ["Cam4", "Cam5"]
    capture.logger = Mock()
    capture.params = {"reconnect": {"max_attempts": 1, "initial_delay_sec": 0, "backoff_step_sec": 0, "max_delay_sec": 0, "min_first_backoff_sec": 0}}
    capture._reconnect_release_done = Event()
    capture._reconnect_release_started_at = time.time()
    capture.release = Mock()
    capture._note_capture_down = Mock()
    capture._abandon_stalled_teardown = Mock()
    capture.pipeline_lock = RLock()
    capture.pipeline = None
    capture.init = Mock(return_value=False)
    capture._last_init_error = None
    capture._noframes_restart_last_ts = 0.0
    capture.subscribers = []
    capture._reconnect_init_thread = None

    started = time.monotonic()
    capture._reconnect_loop()
    elapsed = time.monotonic() - started

    assert elapsed < 5.0
    capture.release.assert_not_called()
    assert capture._reconnect_release_done.is_set()


def test_set_gst_state_null_bounded_returns_after_timeout_and_marks_abandoned():
    from evileye.capture import gstreamer_capture_pipeline as gst_pipeline

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
    element = _Element()
    before = len(gst_pipeline._ORPHANED_GST_NATIVE)

    started = time.monotonic()
    ok = capture._set_gst_state_null_bounded(element, timeout_sec=0.2, label="unit-test")
    elapsed = time.monotonic() - started

    assert ok is False
    assert elapsed < 2.0
    assert capture._pipeline_null_abandoned is True
    assert element in gst_pipeline._ORPHANED_GST_NATIVE
    assert len(gst_pipeline._ORPHANED_GST_NATIVE) >= before + 1
    hung.set()


def test_set_gst_state_null_bounded_orphans_when_finished_not_null():
    from evileye.capture import gstreamer_capture_pipeline as gst_pipeline

    class _Pipeline(GStreamerCapturePipelineMixin):
        pass

    class _Element:
        def set_state(self, _state):
            return None

        def get_state(self, _timeout):
            # Pretend the element is still PLAYING after the NULL request.
            return (None, object(), None)

    capture = _Pipeline()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture._pipeline_null_abandoned = False
    capture._gst_element_is_null = lambda _element: False
    element = _Element()

    ok = capture._set_gst_state_null_bounded(element, timeout_sec=0.2, label="unit-not-null")

    assert ok is False
    assert capture._pipeline_null_abandoned is True
    assert element in gst_pipeline._ORPHANED_GST_NATIVE


def test_reconnect_abandons_stalled_release_and_bumps_generation():
    from evileye.capture import gstreamer_capture_pipeline as gst_pipeline

    class _Frames(GStreamerCaptureFramesMixin, GStreamerCapturePipelineMixin):
        pass

    capture = _Frames()
    capture.pipeline_lock = RLock()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    pipeline = object()
    bus = object()
    appsink = object()
    capture.pipeline = pipeline
    capture.bus = bus
    capture.appsink = appsink
    capture.is_inited = True
    capture.is_working = True
    capture._pipeline_generation = 3
    capture._pipeline_null_abandoned = False
    capture._reconnect_release_started_at = time.time()
    capture._last_sample_wall_ts = 1.0
    capture._record_disconnect = Mock()
    hung = Event()

    def _hang():
        hung.wait(5.0)

    hung_release = Thread(target=_hang, daemon=True)
    hung_teardown = Thread(target=_hang, daemon=True)
    hung_release.start()
    hung_teardown.start()
    capture._reconnect_release_thread = hung_release
    capture._gst_teardown_thread = hung_teardown

    assert capture._reconnect_teardown_still_running() is True
    capture._abandon_stalled_teardown()

    assert capture._reconnect_release_started_at is None
    assert capture._pipeline_null_abandoned is True
    assert capture._pipeline_generation == 4
    assert capture.pipeline is None
    assert capture.appsink is None
    assert capture.is_working is False
    assert capture._reconnect_release_thread is None
    assert capture._gst_teardown_thread is None
    # Hung workers may still be alive, but abandon must unblock init/rebuild.
    assert capture._reconnect_teardown_still_running() is False
    assert pipeline in gst_pipeline._ORPHANED_GST_NATIVE
    assert bus in gst_pipeline._ORPHANED_GST_NATIVE
    assert appsink in gst_pipeline._ORPHANED_GST_NATIVE
    capture._record_disconnect.assert_not_called()
    hung.set()
    hung_release.join(timeout=1.0)
    hung_teardown.join(timeout=1.0)


def test_abandoned_teardown_does_not_block_init_gate():
    """Regression: Cam4/Cam5 stayed dark because init() saw a forever-hung teardown thread."""

    class _Frames(GStreamerCaptureFramesMixin):
        pass

    capture = _Frames()
    capture._pipeline_null_abandoned = False
    capture._reconnect_release_thread = SimpleNamespace(is_alive=lambda: True)
    capture._gst_teardown_thread = SimpleNamespace(is_alive=lambda: True)
    assert capture._reconnect_teardown_still_running() is True

    capture._pipeline_null_abandoned = True
    assert capture._reconnect_teardown_still_running() is False

    capture._detach_abandoned_teardown_workers()
    assert capture._reconnect_release_thread is None
    assert capture._gst_teardown_thread is None
    capture._pipeline_null_abandoned = False
    assert capture._reconnect_teardown_still_running() is False


def test_init_singleflight_blocks_competing_reinit_teardown():
    """Competing init() must not tear down a pipeline another init just built."""
    capture = _capture()
    capture.gstreamer_available = True
    capture.execution_mode = "thread"
    capture._init_singleflight = Lock()
    capture._reconnecting = False
    capture._reconnect_init_thread = None
    capture._pipeline_null_abandoned = True
    capture._reconnect_teardown_still_running = lambda: False
    capture.pipeline = None
    capture.bus = None
    capture.appsink = None
    capture._pipeline_generation = 3
    started = Event()
    release_build = Event()
    calls = []

    def _slow_locked():
        calls.append("build")
        started.set()
        assert release_build.wait(timeout=5.0)
        return True

    capture._init_locked = _slow_locked
    worker = Thread(target=lambda: VideoCaptureGStreamer.init(capture))
    worker.start()
    assert started.wait(timeout=1.0)
    assert capture._init_singleflight.locked()

    competing = VideoCaptureGStreamer.init(capture)
    assert competing is False
    capture.logger.error.assert_called()
    assert any("another init" in str(c) for c in capture.logger.error.call_args_list)
    release_build.set()
    worker.join(timeout=2.0)
    assert not worker.is_alive()
    assert capture._pipeline_null_abandoned is False
    assert calls == ["build"]


def test_init_keeps_abandoned_flag_until_rebuild_succeeds():
    capture = _capture()
    capture.gstreamer_available = True
    capture.execution_mode = "thread"
    capture._init_singleflight = Lock()
    capture._reconnecting = False
    capture._reconnect_init_thread = None
    capture._pipeline_null_abandoned = True
    capture._reconnect_teardown_still_running = lambda: False
    capture.pipeline = object()
    capture.bus = object()
    capture.appsink = object()
    capture._pipeline_generation = 1
    capture._init_locked = lambda: False

    assert VideoCaptureGStreamer.init(capture) is False
    assert capture._pipeline_null_abandoned is True
    assert capture.pipeline is None


def test_teardown_budget_exceeded_detaches_worker_for_rebuild():
    class _Pipeline(GStreamerCapturePipelineMixin, GStreamerCaptureFramesMixin):
        pass

    capture = _Pipeline()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture.gstreamer_available = True
    capture.pipeline_lock = RLock()
    capture.frame_lock = Lock()
    capture._pipeline_generation = 1
    capture._pipeline_null_abandoned = False
    capture._generation_is_current = lambda generation: generation == capture._pipeline_generation
    capture._orphan_gst_native = Mock()
    capture._detach_pipeline_state = Mock(
        return_value={
            "pipeline": object(),
            "bus": object(),
            "appsink": object(),
            "generation": 1,
            "reason": "release",
            "loop": None,
            "recorder": None,
            "bus_handler_id": None,
            "appsink_handler_id": None,
            "main_loop_thread": None,
        }
    )

    def _slow_body(*_args, **_kwargs):
        time.sleep(0.4)

    capture._native_teardown_body = _slow_body
    original_budget = CaptureConstants.TEARDOWN_BUDGET_SEC
    CaptureConstants.TEARDOWN_BUDGET_SEC = 0.05
    try:
        capture._teardown_pipeline("release", join_main_loop=True)
    finally:
        CaptureConstants.TEARDOWN_BUDGET_SEC = original_budget

    assert capture._pipeline_null_abandoned is True
    assert capture._gst_teardown_thread is None
    assert capture._reconnect_teardown_still_running() is False
    capture._orphan_gst_native.assert_called()


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


def test_get_frames_impl_skips_duplicate_single_stream():
    import numpy as np

    image = np.zeros((2, 2, 3), dtype=np.uint8)
    frame = SimpleNamespace(
        frame_id=7,
        connection_generation=1,
        time_stamp=0,
        source_id=0,
        current_video_frame=0,
        current_video_position=0,
        pts_ns=0,
        media_pts_sec=0,
        image=image,
    )
    created = []

    def _create_capture_image(**kwargs):
        created.append(kwargs["frame_id"])
        return SimpleNamespace(**kwargs)

    capture = SimpleNamespace(
        is_working=True,
        _get_call_count=0,
        _get_call_last_log=time.time(),
        split_stream=False,
        frame_lock=Lock(),
        last_frame=frame,
        _last_returned_frame_id=None,
        _same_frame_count=0,
        source_names=["cam"],
        source_address="rtsp://example",
        logger=Mock(),
        subscribers=[],
        _create_capture_image=_create_capture_image,
    )

    first = GStreamerCaptureFramesMixin.get_frames_impl(capture)
    second = GStreamerCaptureFramesMixin.get_frames_impl(capture)
    assert len(first) == 1
    assert second == []
    assert capture._same_frame_count == 1
    frame.frame_id = 8
    third = GStreamerCaptureFramesMixin.get_frames_impl(capture)
    assert len(third) == 1
    assert created == [7, 8]


def test_release_does_not_clear_flags_of_a_newer_generation():
    capture = _capture()
    capture._pipeline_generation = 2
    capture.pipeline = object()

    def _teardown(*_args, **_kwargs):
        capture._pipeline_generation = 3

    capture._teardown_pipeline = Mock(side_effect=_teardown)
    capture._generation_is_current = lambda generation: capture._pipeline_generation == generation

    VideoCaptureGStreamer.release(capture)

    capture._teardown_pipeline.assert_called_once_with(
        "release", join_main_loop=True, expected_generation=2
    )
    assert capture.is_inited is True
    assert capture.is_working is True


def test_begin_reconnect_release_does_not_start_a_second_release():
    calls = []
    capture = SimpleNamespace(
        source_names=["cam"],
        logger=Mock(),
        _reconnect_release_thread=SimpleNamespace(is_alive=lambda: True),
        _reconnect_release_done=Event(),
        release=lambda: calls.append("release"),
        _abandon_stalled_teardown=lambda: calls.append("abandon"),
    )
    capture._reconnect_release_done.set()

    GStreamerCaptureFramesMixin._begin_reconnect_release(capture, 0.01)

    assert calls == []


def test_restart_script_uses_detach_and_survived_kill_error():
    from pathlib import Path

    text = Path("evileye/deploy_monitor/scripts/restart_evileye.sh").read_text(encoding="utf-8")
    assert "--detach" in text
    assert "survived SIGKILL" in text
    assert 'Child already running after stop (another agent)' not in text
    assert CaptureConstants.RECONNECT_RELEASE_WAIT_SEC > 0
    assert CaptureConstants.TEARDOWN_NULL_TIMEOUT_SEC > 0
