from __future__ import annotations

import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugin_runtime import ItemModuleAdapter
from evileye.core.plugins import plugin_registry
from evileye.object_detector.object_detection_base import (
    DetectionResult,
    DetectionResultList,
)
from evileye.object_tracker.object_tracking_botsort import ObjectTrackingBotsort
from evileye.object_tracker.tracking_results import TrackingResultList


def _detection(source_id: int, frame_id: int) -> DetectionResultList:
    result = DetectionResultList()
    result.source_id = source_id
    result.frame_id = frame_id
    result.detections = [DetectionResult()]
    return result


def _frame(source_id: int, frame_id: int) -> Frame:
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.image = np.zeros((8, 8, 3), dtype=np.uint8)
    return frame


def test_botsort_plugin_keeps_tracker_state_per_source(monkeypatch):
    import evileye.object_tracker.object_tracking_botsort as botsort_module

    created_trackers = []
    updated_trackers = []

    class FakeTracker:
        def __init__(self, _cfg, _encoders, frame_rate):
            self.frame_rate = frame_rate
            self.reset_count = 0
            created_trackers.append(self)

        def reset(self):
            self.reset_count += 1

    def fake_update(tracker, _detections, _image, time_stamp=None):
        updated_trackers.append(tracker)
        result = TrackingResultList()
        result.time_stamp = time_stamp
        return result

    monkeypatch.setattr(botsort_module, "BOTSORT", FakeTracker)
    monkeypatch.setattr(botsort_module, "run_tracker_update", fake_update)
    module = ObjectTrackingBotsort()
    state = module.create_state({"fps": 12}, context=None)

    module.process_item((_detection(1, 10), _frame(1, 10)), state)
    module.process_item((_detection(2, 4), _frame(2, 4)), state)
    module.process_item((_detection(1, 1), _frame(1, 1)), state)

    assert len(created_trackers) == 2
    assert created_trackers[0] is not created_trackers[1]
    assert updated_trackers == [created_trackers[0], created_trackers[1], created_trackers[0]]
    assert created_trackers[0].reset_count == 1
    assert created_trackers[1].reset_count == 0


def test_botsort_plugin_reads_shared_frame_handle_without_consuming_it():
    from evileye.core.frame_transport import SharedFrameTransport

    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.full((4, 5, 3), 9, dtype=np.uint8), frame_id=3, timestamp=1.0
    )
    frame = Frame()
    frame.frame_id = 3
    frame.frame_handle = handle
    module = ObjectTrackingBotsort()
    state = module.create_state({}, context=None)

    try:
        image = module._plugin_image(frame, state)
        assert image.shape == (4, 5, 3)
        assert image[0, 0, 0] == 9
        # A following stage still owns the descriptor and can materialize it.
        assert owner.get_frame_view(handle)[0, 0, 0] == 9
    finally:
        module.close()
        owner.release_frame(handle)


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_botsort_plugin_emits_empty_result_per_frame(execution_mode):
    registered = plugin_registry.get_module("ObjectTrackingBotsort")
    assert registered is not None
    assert registered.spec.kind == "processor_item"

    adapter = EvilEyeBase.create_instance("ObjectTrackingBotsort")
    assert isinstance(adapter, ItemModuleAdapter)
    adapter.set_params(
        module_id="ObjectTrackingBotsort",
        execution_mode=execution_mode,
        source_ids=[7],
        fps=5,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        assert adapter.is_ready(60), "tracker worker did not finish initialization"
        frame = _frame(7, 1)
        frame.connection_generation = 3
        empty = DetectionResultList()
        empty.source_id = 7
        empty.frame_id = 1
        assert adapter.put((empty, frame)) is None

        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.01)

        assert output is not None
        tracks, output_frame = output
        assert isinstance(tracks, TrackingResultList)
        assert tracks.source_id == 7
        assert tracks.frame_id == 1
        assert output_frame.frame_id == 1
        assert output_frame.connection_generation == 3
    finally:
        adapter.stop()
        adapter.release()


def test_surveillance_encoder_setup_is_per_module(monkeypatch):
    import logging
    from types import SimpleNamespace

    from evileye.core.plugins import plugin_registry
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    legacy_registered = SimpleNamespace(
        spec=SimpleNamespace(
            kind="tracker",
            default_execution_mode="thread",
            execution_modes=("thread", "process"),
        )
    )
    original_get_module = plugin_registry.get_module
    monkeypatch.setattr(
        plugin_registry,
        "get_module",
        lambda module_id: (
            legacy_registered
            if module_id == "test/legacy-tracker"
            else original_get_module(module_id)
        ),
    )
    import evileye.object_tracker.trackers.onnx_encoder as encoder_module
    monkeypatch.setattr(
        encoder_module,
        "OnnxEncoder",
        lambda path: f"encoder:{path}",
    )

    pipeline = object.__new__(PipelineSurveillance)
    pipeline.logger = logging.getLogger("test.botsort_encoder_setup")
    pipeline._init_encoders([
        {
            "type": "test/legacy-tracker",
            "execution_mode": "thread",
            "tracker_onnx": "legacy.onnx",
        },
        {
            "type": "ObjectTrackingBotsort",
            "execution_mode": "thread",
            "tracker_onnx": "unused.onnx",
        },
    ])

    assert pipeline.encoders == {"legacy.onnx": "encoder:legacy.onnx"}


def test_surveillance_tracker_mode_uses_module_default():
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    assert PipelineSurveillance._trackers_use_process_mode(
        [{"type": "ObjectTrackingBotsort"}]
    )
    assert not PipelineSurveillance._trackers_use_process_mode(
        [{"type": "ObjectTrackingBotsort", "execution_mode": "thread"}]
    )


def test_botsort_plugin_process_serializes_live_tracking_output():
    adapter = EvilEyeBase.create_instance("ObjectTrackingBotsort")
    adapter.set_params(
        module_id="ObjectTrackingBotsort",
        execution_mode="process",
        source_ids=[2],
        fps=5,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        assert adapter.is_ready(60), "tracker worker did not finish initialization"
        frame = _frame(2, 1)
        frame.image = np.zeros((48, 48, 3), dtype=np.uint8)
        detection = DetectionResult()
        detection.bounding_box = [8, 8, 36, 36]
        detection.class_id = 0
        detection.confidence = 0.95
        detections = DetectionResultList()
        detections.source_id = 2
        detections.frame_id = 1
        detections.detections = [detection]
        adapter.put((detections, frame))

        deadline = time.monotonic() + 20.0
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.02)

        assert output is not None
        tracks, output_frame = output
        assert tracks.source_id == 2
        assert tracks.frame_id == 1
        assert len(tracks.tracks) == 1
        assert "track_object" in tracks.tracks[0].tracking_data
        assert output_frame.frame_id == 1
    finally:
        adapter.stop()
        adapter.release()


def test_botsort_plugin_resets_source_tracker_on_connection_generation_change(monkeypatch):
    import evileye.object_tracker.object_tracking_botsort as botsort_module

    created_trackers = []

    class FakeTracker:
        def __init__(self, _cfg, _encoders, frame_rate):
            self.frame_rate = frame_rate
            self.reset_count = 0
            created_trackers.append(self)

        def reset(self):
            self.reset_count += 1

    monkeypatch.setattr(botsort_module, "BOTSORT", FakeTracker)
    monkeypatch.setattr(
        botsort_module,
        "run_tracker_update",
        lambda tracker, _detections, _image, time_stamp=None: TrackingResultList(),
    )
    module = ObjectTrackingBotsort()
    state = module.create_state({"fps": 12}, context=None)
    first_frame = _frame(1, 10)
    first_frame.connection_generation = 0
    second_frame = _frame(1, 11)
    second_frame.connection_generation = 1

    module.process_item((_detection(1, 10), first_frame), state)
    module.process_item((_detection(1, 11), second_frame), state)

    assert len(created_trackers) == 1
    assert created_trackers[0].reset_count == 1


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_botsort_item_runtime_preserves_track_continuity(execution_mode):
    import cv2

    adapter = EvilEyeBase.create_instance("ObjectTrackingBotsort")
    adapter.set_params(
        module_id="ObjectTrackingBotsort",
        execution_mode=execution_mode,
        source_ids=[7],
        fps=10,
    )
    assert adapter.init() is True
    adapter.start()
    track_ids = []
    try:
        assert adapter.is_ready(60), "tracker worker did not finish initialization"
        for frame_id in range(1, 6):
            x1 = 60 + frame_id * 3
            image = np.zeros((240, 320, 3), dtype=np.uint8)
            cv2.rectangle(image, (x1, 80), (x1 + 50, 180), (255, 255, 255), -1)
            frame = Frame()
            frame.source_id = 7
            frame.frame_id = frame_id
            frame.time_stamp = frame_id / 10
            frame.image = image

            detection = DetectionResult()
            detection.bounding_box = [x1, 80, x1 + 50, 180]
            detection.confidence = 0.95
            detection.class_id = 0
            detections = DetectionResultList()
            detections.source_id = 7
            detections.frame_id = frame_id
            detections.time_stamp = frame.time_stamp
            detections.detections = [detection]
            adapter.put((detections, frame))

            deadline = time.monotonic() + (15.0 if execution_mode == "process" else 3.0)
            output = None
            while output is None and time.monotonic() < deadline:
                candidate = adapter.get()
                if candidate is not None and candidate[0].frame_id == frame_id:
                    output = candidate
                elif candidate is None:
                    time.sleep(0.01)
            assert output is not None, f"no tracker output for frame {frame_id}"
            tracks, output_frame = output
            assert output_frame.frame_id == frame_id
            assert len(tracks.tracks) == 1
            track_ids.append(tracks.tracks[0].track_id)
        assert len(set(track_ids)) == 1
    finally:
        adapter.stop()
        adapter.release()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_botsort_matches_legacy_frame_sequence_golden(execution_mode):
    """Keep the migrated SPI tracker aligned with the pre-SPI tracker output.

    Golden values were captured from the legacy worker at 27fcb2a with the same
    deterministic detections, image, and BoT-SORT configuration.
    """
    adapter = EvilEyeBase.create_instance("ObjectTrackingBotsort")
    adapter.set_params(
        module_id="ObjectTrackingBotsort",
        execution_mode=execution_mode,
        source_ids=[1],
        fps=5,
        botsort_cfg={"gmc_method": "none", "track_buffer": 3},
    )
    assert adapter.init() is True
    adapter.start()

    image = np.zeros((96, 128, 3), dtype=np.uint8)
    positions = [(10, 20), (12, 20), None, (16, 21), (18, 22), None, None, (24, 23)]
    expected_boxes = [
        [10.0, 20.0, 40.0, 60.0],
        [11.7355, 20.0, 41.7355, 60.0],
        None,
        [15.151, 20.7796, 45.151, 60.7796],
        [17.7172, 21.7874, 47.7172, 61.7874],
        None,
        None,
        [22.869, 22.829, 52.869, 62.829],
    ]

    try:
        assert adapter.is_ready(60), "tracker worker did not finish initialization"
        for frame_id, position in enumerate(positions, 1):
            detections = DetectionResultList()
            detections.source_id = 1
            detections.frame_id = frame_id
            detections.detections = []
            if position is not None:
                x, y = position
                detection = DetectionResult()
                detection.bounding_box = [x, y, x + 30, y + 40]
                detection.class_id = 0
                detection.confidence = 0.95
                detections.detections = [detection]

            frame = _frame(1, frame_id)
            frame.image = image.copy()
            adapter.put((detections, frame))

            deadline = time.monotonic() + (20.0 if execution_mode == "process" else 3.0)
            output = None
            while output is None and time.monotonic() < deadline:
                output = adapter.get()
                if output is None:
                    time.sleep(0.01)

            assert output is not None, f"no tracker output for frame {frame_id}"
            tracks, output_frame = output
            assert output_frame.frame_id == frame_id
            assert tracks.source_id == 1
            assert tracks.frame_id == frame_id
            expected_box = expected_boxes[frame_id - 1]
            if expected_box is None:
                assert tracks.tracks == []
            else:
                assert len(tracks.tracks) == 1
                track = tracks.tracks[0]
                assert track.track_id == 1
                assert track.class_id == 0
                assert track.confidence == pytest.approx(0.95, abs=1e-5)
                assert track.bounding_box == pytest.approx(expected_box, abs=0.035)
    finally:
        adapter.stop()
        adapter.release()
