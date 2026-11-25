from __future__ import annotations

import pytest
from evileye.video_recorder.continuous_recorder_gst import (
    GstBranchRefs,
    GstContinuousRecorder,
)
from evileye.video_recorder.recorder_base import SourceMeta
from evileye.video_recorder.recording_params import RecordingParams


def test_stop_with_pipeline_sends_eos_before_disabling_recording_branch(tmp_path):
    operations = []

    class FakePad:
        def push_event(self, event):
            operations.append(("eos", event))
            return True

    class FakeElement:
        def __init__(self, name, parent):
            self.name = name
            self.parent = parent

        def get_static_pad(self, name):
            assert name == "src"
            return FakePad()

        def get_property(self, name):
            assert name == "current-level-buffers"
            return 0

        def set_state(self, state):
            operations.append(("state", self.name, state))

        def get_parent(self):
            return self.parent

    class FakePipeline:
        def remove(self, element):
            operations.append(("remove", element.name))

    class FakeEvent:
        @staticmethod
        def new_eos():
            return "eos-event"

    class FakeState:
        NULL = "NULL"

    class FakeGst:
        Event = FakeEvent
        State = FakeState

    pipeline = FakePipeline()
    elements = {
        name: FakeElement(name, pipeline)
        for name in (
            "recording_queue",
            "videoconvert",
            "capsfilter",
            "x264enc",
            "h264parse",
            "queue_before_mux",
            "splitmuxsink",
        )
    }
    recorder = GstContinuousRecorder()
    recorder.start(
        SourceMeta("Cam1", None, "test", source_names=["Cam1"]),
        RecordingParams(
            enabled=True,
            continuous_recording_enabled=True,
            out_dir=str(tmp_path),
            min_file_size_kb=0,
        ),
    )
    recorder._recording_out_dir = tmp_path
    recorder._recording_out_dirs = {tmp_path}
    recorder._recording_container = "mp4"
    recorder._session_has_buffer = True
    recorder._refs = GstBranchRefs(**elements)

    recorder.stop_with_pipeline(pipeline=pipeline, Gst=FakeGst)

    assert operations[0] == ("eos", "eos-event")
    assert operations[1] == ("state", "videoconvert", "NULL")
    assert recorder._refs is None


def test_native_teardown_nulls_pipeline_after_splitmux_detach():
    """After recorder detaches splitmux, capture teardown must NULL the RTSP pipeline."""
    from threading import Event, Lock, RLock
    from types import SimpleNamespace
    from unittest.mock import Mock

    from evileye.capture.gstreamer_capture_pipeline import GStreamerCapturePipelineMixin
    from evileye.capture.gstreamer_capture_frames import GStreamerCaptureFramesMixin

    class _Capture(GStreamerCapturePipelineMixin, GStreamerCaptureFramesMixin):
        pass

    null_calls = []
    orphan_calls = []

    capture = _Capture()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture.pipeline_lock = RLock()
    capture.frame_lock = Lock()
    capture.frame_buffer = SimpleNamespace(empty=lambda: True)
    capture.last_frame = None
    capture._fps_times = []
    capture._pipeline_generation = 1
    capture._pipeline_null_abandoned = False
    capture._teardown_cancel = Event()
    capture._gst_continuous_recorder = object()
    capture._set_gst_state_null_bounded = lambda *a, **k: null_calls.append((a, k)) or True
    capture._orphan_gst_native = lambda *objs: orphan_calls.extend([o for o in objs if o is not None])
    flush_calls = []
    capture._flush_recording_queue = lambda *a, **k: flush_calls.append((a, k))
    capture._cleanup_recording_branch = Mock()
    capture._stop_notify_worker = Mock()
    capture._maybe_schedule_malloc_trim = Mock()
    capture._generation_is_current = lambda generation: generation == capture._pipeline_generation
    # Detach succeeded: splitmux is no longer a child.
    capture._pipeline_has_attached_splitmux = lambda _pipeline: False

    recorder = Mock()
    pipeline = object()
    state = {
        "pipeline": pipeline,
        "bus": object(),
        "appsink": object(),
        "generation": 1,
        "reason": "release",
        "recorder": recorder,
        "loop": None,
        "main_loop_thread": None,
        "bus_handler_id": None,
        "appsink_handler_id": None,
    }

    capture._native_teardown_body(state, join_main_loop=False)

    recorder.stop_with_pipeline.assert_called_once()
    kwargs = recorder.stop_with_pipeline.call_args.kwargs
    assert kwargs.get("finalize") is False
    assert flush_calls == [], "recording_queue flush/NULL truncates open splitmux"
    assert len(null_calls) == 1, "detached splitmux must allow capture pipeline NULL"
    assert pipeline not in orphan_calls


def test_native_teardown_skips_null_while_splitmux_still_attached():
    """If detach failed, never NULL a pipeline that still owns splitmux."""
    from threading import Event, Lock, RLock
    from types import SimpleNamespace
    from unittest.mock import Mock

    from evileye.capture.gstreamer_capture_pipeline import GStreamerCapturePipelineMixin
    from evileye.capture.gstreamer_capture_frames import GStreamerCaptureFramesMixin

    class _Capture(GStreamerCapturePipelineMixin, GStreamerCaptureFramesMixin):
        pass

    null_calls = []
    orphan_calls = []

    capture = _Capture()
    capture.logger = Mock()
    capture.source_names = ["Cam4", "Cam5"]
    capture.pipeline_lock = RLock()
    capture.frame_lock = Lock()
    capture.frame_buffer = SimpleNamespace(empty=lambda: True)
    capture.last_frame = None
    capture._fps_times = []
    capture._pipeline_generation = 1
    capture._pipeline_null_abandoned = False
    capture._teardown_cancel = Event()
    capture._set_gst_state_null_bounded = lambda *a, **k: null_calls.append((a, k)) or True
    capture._orphan_gst_native = lambda *objs: orphan_calls.extend([o for o in objs if o is not None])
    capture._flush_recording_queue = lambda *a, **k: None
    capture._cleanup_recording_branch = Mock()
    capture._stop_notify_worker = Mock()
    capture._maybe_schedule_malloc_trim = Mock()
    capture._generation_is_current = lambda generation: generation == capture._pipeline_generation
    capture._pipeline_has_attached_splitmux = lambda _pipeline: True

    recorder = Mock()
    pipeline = object()
    state = {
        "pipeline": pipeline,
        "bus": object(),
        "appsink": object(),
        "generation": 1,
        "reason": "release",
        "recorder": recorder,
        "loop": None,
        "main_loop_thread": None,
        "bus_handler_id": None,
        "appsink_handler_id": None,
    }

    capture._native_teardown_body(state, join_main_loop=False)

    assert null_calls == []
    assert pipeline in orphan_calls
    assert capture._pipeline_null_abandoned is True


def test_detached_branch_eos_uses_muxer_when_queue_pad_is_unlinked():
    """bin.remove() unlinks pads, so queue.push_event(EOS) fails; the muxer still can."""
    from evileye.video_recorder.continuous_recorder_gst import push_eos_to_detached_branch

    class _Pad:
        def __init__(self):
            self.peer = None

        def get_peer(self):
            return self.peer

        def push_event(self, _event):
            return False

        def link(self, _sink):
            raise AssertionError("unlinked queue pad must not be required")

    class _Queue:
        def get_static_pad(self, _name):
            return _Pad()

    class _Mux:
        def __init__(self):
            self.events = []

        def send_event(self, event):
            self.events.append(event)
            return True

        def get_static_pad(self, _name):
            return None

    class _Gst:
        class Event:
            @staticmethod
            def new_eos():
                return "eos"

    mux = _Mux()
    assert push_eos_to_detached_branch(_Queue(), mux, gst=_Gst) is True
    assert mux.events == ["eos"]


def test_stop_with_pipeline_abandon_skips_splitmux_null(tmp_path):
    """Abandon must detach splitmux without set_state(NULL) — NULL truncates to 0B."""
    operations = []

    class FakePad:
        def __init__(self):
            self._peer = FakePad.__new__(FakePad)
            self._peer._peer = None

        def push_event(self, event):
            operations.append(("eos", event))
            return True

        def send_event(self, event):
            operations.append(("flush", event))

        def get_peer(self):
            return self._peer

        def unlink(self, peer):
            operations.append(("unlink", peer))

    class FakeElement:
        def __init__(self, name, parent):
            self.name = name
            self.parent = parent
            self._pad = FakePad()

        def get_static_pad(self, name):
            return self._pad

        def set_property(self, *_args):
            return None

        def set_state(self, state):
            operations.append(("state", self.name, state))

        def get_parent(self):
            return self.parent

        def get_name(self):
            return self.name

    class FakePipeline:
        def __init__(self):
            self.elements = {}

        def add(self, element):
            self.elements[element.name] = element
            element.parent = self

        def remove(self, element):
            operations.append(("remove", element.name))
            self.elements.pop(element.name, None)
            element.parent = None

        def get_by_name(self, name):
            return self.elements.get(name)

    class FakeEvent:
        @staticmethod
        def new_eos():
            return "eos-event"

        @staticmethod
        def new_flush_start():
            return "flush-start"

        @staticmethod
        def new_flush_stop(_):
            return "flush-stop"

    class FakeState:
        NULL = "NULL"

    class FakeGst:
        Event = FakeEvent
        State = FakeState
        SECOND = 1

    pipeline = FakePipeline()
    elements = {
        name: FakeElement(name, pipeline)
        for name in (
            "recording_queue",
            "videoconvert",
            "capsfilter",
            "x264enc",
            "h264parse",
            "queue_before_mux",
            "splitmuxsink",
        )
    }
    for name, elem in elements.items():
        if name != "recording_queue":
            pipeline.elements[name] = elem
    # recording_queue stays in the capture pipeline (name in pipeline string).
    pipeline.elements["recording_queue"] = elements["recording_queue"]
    elements["splitmuxsink"].name = "recording_splitmuxsink"
    pipeline.elements["recording_splitmuxsink"] = elements["splitmuxsink"]
    pipeline.elements.pop("splitmuxsink", None)

    recorder = GstContinuousRecorder()
    recorder.start(
        SourceMeta("Cam4", None, "test", source_names=["Cam4", "Cam5"]),
        RecordingParams(
            enabled=True,
            continuous_recording_enabled=True,
            out_dir=str(tmp_path),
            min_file_size_kb=0,
        ),
    )
    recorder._session_has_buffer = True
    recorder._refs = GstBranchRefs(**elements)

    recorder.stop_with_pipeline(pipeline=pipeline, Gst=FakeGst, finalize=False)

    assert ("eos", "eos-event") not in operations
    assert ("state", "splitmuxsink", "NULL") not in operations
    assert ("state", "recording_splitmuxsink", "NULL") not in operations
    assert ("state", "videoconvert", "NULL") not in operations
    assert ("remove", "recording_splitmuxsink") in operations
    assert ("remove", "videoconvert") in operations
    assert elements["splitmuxsink"].parent is None
    assert "recording_queue" in pipeline.elements
    assert recorder._refs is None


def test_stop_with_pipeline_cancel_during_finalize_skips_null(tmp_path, monkeypatch):
    import threading

    operations = []
    cancel = threading.Event()

    class FakePad:
        def push_event(self, event):
            operations.append(("eos", event))
            cancel.set()  # abandon mid-finalize
            return True

        def send_event(self, event):
            return None

    class FakeElement:
        def __init__(self, name, parent):
            self.name = name
            self.parent = parent

        def get_static_pad(self, _name):
            return FakePad()

        def get_property(self, name):
            assert name == "current-level-buffers"
            return 1  # keep finalize loop running until cancel is seen

        def set_property(self, *_args):
            return None

        def set_state(self, state):
            operations.append(("state", self.name, state))

        def get_parent(self):
            return self.parent

    class FakePipeline:
        def remove(self, element):
            operations.append(("remove", element.name))

    class FakeEvent:
        @staticmethod
        def new_eos():
            return "eos-event"

        @staticmethod
        def new_flush_start():
            return "flush-start"

        @staticmethod
        def new_flush_stop(_):
            return "flush-stop"

    class FakeState:
        NULL = "NULL"

    class FakeGst:
        Event = FakeEvent
        State = FakeState
        SECOND = 1

    pipeline = FakePipeline()
    elements = {
        name: FakeElement(name, pipeline)
        for name in (
            "recording_queue",
            "videoconvert",
            "capsfilter",
            "x264enc",
            "h264parse",
            "queue_before_mux",
            "splitmuxsink",
        )
    }
    recorder = GstContinuousRecorder()
    recorder.start(
        SourceMeta("Cam4", None, "test", source_names=["Cam4"]),
        RecordingParams(enabled=True, continuous_recording_enabled=True, out_dir=str(tmp_path)),
    )
    recorder._session_has_buffer = True
    recorder._recording_out_dirs = {tmp_path}
    recorder._recording_container = "mp4"
    recorder._refs = GstBranchRefs(**elements)
    monkeypatch.setenv("EVILEYE_RECORDING_FINALIZE_SEC", "2")

    recorder.stop_with_pipeline(
        pipeline=pipeline, Gst=FakeGst, finalize=True, cancel_event=cancel
    )

    assert ("eos", "eos-event") in operations
    assert ("state", "splitmuxsink", "NULL") not in operations
    assert recorder._refs is None


def test_stop_without_any_muxed_buffer_skips_blocking_eos(tmp_path):
    operations = []

    class FakePad:
        def push_event(self, event):
            operations.append(("eos", event))
            return True

    class FakeElement:
        def __init__(self, name, parent):
            self.name = name
            self.parent = parent

        def get_static_pad(self, name):
            assert name == "src"
            return FakePad()

        def set_state(self, state):
            operations.append(("state", self.name, state))

        def get_parent(self):
            return self.parent

    class FakePipeline:
        def remove(self, element):
            operations.append(("remove", element.name))

    class FakeEvent:
        @staticmethod
        def new_eos():
            return "eos-event"

    class FakeState:
        NULL = "NULL"

    class FakeGst:
        Event = FakeEvent
        State = FakeState

    pipeline = FakePipeline()
    elements = {
        name: FakeElement(name, pipeline)
        for name in (
            "recording_queue",
            "videoconvert",
            "capsfilter",
            "x264enc",
            "h264parse",
            "queue_before_mux",
            "splitmuxsink",
        )
    }
    recorder = GstContinuousRecorder()
    recorder.start(
        SourceMeta("Cam1", None, "test", source_names=["Cam1"]),
        RecordingParams(enabled=True, continuous_recording_enabled=True, out_dir=str(tmp_path)),
    )
    recorder._refs = GstBranchRefs(**elements)

    recorder.stop_with_pipeline(pipeline=pipeline, Gst=FakeGst)

    assert ("eos", "eos-event") not in operations
    assert ("state", "videoconvert", "NULL") in operations
    assert recorder._refs is None


def test_failed_recording_branch_attachment_removes_partial_elements(tmp_path):
    class FakeElement:
        def __init__(self, name):
            self.name = name
            self.parent = None
            self.properties = {}
            self.state = None

        def set_property(self, name, value):
            self.properties[name] = value

        def connect(self, *_args):
            return 1

        def link(self, _other):
            return True

        def get_static_pad(self, _name):
            return None

        def set_state(self, state):
            self.state = state

        def get_parent(self):
            return self.parent

    class RecordingQueue(FakeElement):
        def link(self, _other):
            return False

    class FakeFactory:
        def __init__(self):
            self.created = []

        def make(self, _factory, name):
            element = FakeElement(name)
            self.created.append(element)
            return element

    class FakeCaps:
        @staticmethod
        def from_string(_caps):
            return object()

    class FakeState:
        NULL = "NULL"
        READY = "READY"

    class FakeStateChangeReturn:
        FAILURE = "FAILURE"

    class FakeGst:
        ElementFactory = FakeFactory()
        Caps = FakeCaps
        State = FakeState
        StateChangeReturn = FakeStateChangeReturn
        SECOND = 1

    class FakePipeline:
        def __init__(self):
            self.elements = []

        def add(self, element):
            element.parent = self
            self.elements.append(element)

        def remove(self, element):
            self.elements.remove(element)
            element.parent = None

        def get_state(self, _timeout):
            return "SUCCESS", FakeState.READY, None

    pipeline = FakePipeline()
    recording_queue = RecordingQueue("recording_queue")
    recording_queue.parent = pipeline
    recorder = GstContinuousRecorder()
    recorder.start(
        SourceMeta("Cam1", "video.mp4", "test", source_names=["Cam1"]),
        RecordingParams(
            enabled=True,
            continuous_recording_enabled=True,
            out_dir=str(tmp_path),
            min_file_size_kb=0,
        ),
    )

    with pytest.raises(RuntimeError, match="recording queue to videoconvert"):
        recorder.start_with_pipeline(
            pipeline=pipeline,
            recording_queue_elem=recording_queue,
            Gst=FakeGst,
        )

    assert pipeline.elements == []
    assert all(element.parent is None for element in FakeGst.ElementFactory.created)
    assert recorder._refs is None
    assert recorder.is_running is False
