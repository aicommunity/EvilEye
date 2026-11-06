from types import SimpleNamespace

import pytest

from evileye.capture.gstreamer_capture_recording import GStreamerCaptureRecordingMixin


class _Pipeline:
    def __init__(self, recording_queue=True):
        self.recording_queue = object() if recording_queue else None

    def get_by_name(self, name):
        assert name == "recording_queue"
        return self.recording_queue


class _Recorder:
    def __init__(self, *, setup_error=None):
        self.setup_error = setup_error
        self.started = None
        self.attached = None
        self.stopped = None
        self._refs = None

    def start(self, source, params):
        self.started = (source, params)

    def start_with_pipeline(self, *, pipeline, recording_queue_elem, Gst):
        self.attached = (pipeline, recording_queue_elem, Gst)
        if self.setup_error:
            raise self.setup_error
        self._refs = object()

    def stop_with_pipeline(self, *, pipeline, Gst):
        self.stopped = (pipeline, Gst)
        self._refs = None


def _capture(recorder, *, enabled=True, continuous=True, has_queue=True):
    return SimpleNamespace(
        recording_params=SimpleNamespace(
            enabled=enabled,
            continuous_recording_enabled=continuous,
        ),
        pipeline=_Pipeline(recording_queue=has_queue),
        source_names=["camera-1"],
        source_ids=[1],
        source_address="video.mp4",
        source_type="VideoFile",
        source_fps=25,
        _gst_continuous_recorder=recorder,
        _recording_queue_elem=None,
    )


def test_recording_branch_uses_only_the_shared_recorder(monkeypatch):
    import evileye.capture.gstreamer_capture_recording as recording_module

    recorder = _Recorder()
    capture = _capture(recorder)
    monkeypatch.setattr(recording_module, "GstContinuousRecorder", lambda: recorder)

    GStreamerCaptureRecordingMixin._setup_recording_branch(capture)

    assert recorder.started is not None
    assert recorder.started[0].source_name == "camera-1"
    assert recorder.attached is not None
    assert capture._recording_queue_elem is capture.pipeline.recording_queue
    assert not hasattr(capture, "_recording_elements")
    GStreamerCaptureRecordingMixin._cleanup_recording_branch(capture)
    assert recorder.stopped[0] is capture.pipeline
    assert capture._recording_queue_elem is None


def test_enabled_recording_without_pipeline_queue_fails_explicitly(monkeypatch):
    import evileye.capture.gstreamer_capture_recording as recording_module

    recorder = _Recorder()
    capture = _capture(recorder, has_queue=False)
    monkeypatch.setattr(recording_module, "GstContinuousRecorder", lambda: recorder)

    with pytest.raises(RuntimeError, match="no recording_queue"):
        GStreamerCaptureRecordingMixin._setup_recording_branch(capture)
    assert recorder.started is None
    assert recorder.attached is None


def test_shared_recorder_setup_failure_is_not_swallowed_or_retried_inline(monkeypatch):
    import evileye.capture.gstreamer_capture_recording as recording_module

    recorder = _Recorder(setup_error=RuntimeError("encoder setup failed"))
    capture = _capture(recorder)
    monkeypatch.setattr(recording_module, "GstContinuousRecorder", lambda: recorder)

    with pytest.raises(RuntimeError, match="encoder setup failed"):
        GStreamerCaptureRecordingMixin._setup_recording_branch(capture)
    assert recorder.attached is not None
    assert not hasattr(capture, "_recording_elements")


def test_disabled_recording_does_not_create_a_branch(monkeypatch):
    import evileye.capture.gstreamer_capture_recording as recording_module

    recorder = _Recorder()
    capture = _capture(recorder, enabled=False)
    monkeypatch.setattr(recording_module, "GstContinuousRecorder", lambda: recorder)

    GStreamerCaptureRecordingMixin._setup_recording_branch(capture)

    assert recorder.started is None
    assert recorder.attached is None
