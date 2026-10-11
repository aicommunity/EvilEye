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
