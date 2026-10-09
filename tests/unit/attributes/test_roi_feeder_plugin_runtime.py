from __future__ import annotations

import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugin_runtime import ItemModuleAdapter
from evileye.object_tracker.tracking_results import TrackingResult, TrackingResultList


def _tracking_frame(frame_id: int):
    tracking = TrackingResultList()
    track = TrackingResult()
    track.track_id = 10
    track.class_id = 0
    track.bounding_box = [2, 2, 8, 8]
    tracking.tracks.append(track)

    frame = Frame()
    frame.source_id = 1
    frame.frame_id = frame_id
    frame.image = np.zeros((12, 12, 3), dtype=np.uint8)
    return tracking, frame


def _get_result(processor, timeout: float):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = processor.get()
        if result is not None:
            return result
        time.sleep(0.02)
    return None


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_builtin_roi_feeder_uses_common_item_runtime(execution_mode):
    from evileye.attributes_detection.roi_feeder import RoiFeeder
    from evileye.core.plugins import plugin_registry

    registered = plugin_registry.get_module("evileye/RoiFeeder")
    assert registered is not None
    assert registered.spec.factory is RoiFeeder
    assert registered.spec.kind == "processor_item"

    processor = EvilEyeBase.create_instance("RoiFeeder")
    assert isinstance(processor, ItemModuleAdapter)
    processor.set_params(
        type="RoiFeeder",
        execution_mode=execution_mode,
        source_ids=[1],
        padding=0.2,
        every_n_frames=2,
        queue_size=2,
    )
    assert processor.init() is True
    processor.start()
    try:
        first = _tracking_frame(1)
        second = _tracking_frame(2)
        processor.put(first)
        processor.put(second)

        timeout = 45.0 if execution_mode == "process" else 3.0
        first_result = _get_result(processor, timeout)
        second_result = _get_result(processor, timeout)

        assert first_result is not None
        assert second_result is not None
        assert first_result[1].frame_id == 1
        assert not hasattr(first_result[0], "roi_data")
        assert second_result[1].frame_id == 2
        assert second_result[0].roi_data == [
            {"track_id": 10, "roi_bbox": [1, 1, 9, 9], "class_id": 0}
        ]
    finally:
        processor.stop()


def test_legacy_roi_config_selects_generic_item_adapter():
    from evileye.pipelines.pipeline_surveillance import PipelineSurveillance

    pipeline = PipelineSurveillance()
    pipeline._init_attributes_roi(
        [{"type": "RoiFeeder", "source_ids": [1], "execution_mode": "thread"}]
    )

    stage_processors = pipeline.processors[0].get_processors()
    assert len(stage_processors) == 1
    assert isinstance(stage_processors[0], ItemModuleAdapter)
    assert stage_processors[0].registered_module.qualified_id == "evileye/RoiFeeder"
