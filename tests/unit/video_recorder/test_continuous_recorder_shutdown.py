from __future__ import annotations

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
    recorder._refs = GstBranchRefs(**elements)

    recorder.stop_with_pipeline(pipeline=pipeline, Gst=FakeGst)

    assert operations[0] == ("eos", "eos-event")
    assert operations[1] == ("state", "videoconvert", "NULL")
    assert recorder._refs is None
