"""Opt-in smoke tests for real attribute modules in spawn workers."""

import os
import time
from pathlib import Path

import numpy as np
import pytest

from evileye.attributes_detection.attribute_classifier import AttributeClassifier
from evileye.attributes_detection.attribute_detector import AttributeDetector
from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.frame_transport import SharedFrameTransport
from evileye.object_tracker.tracking_results import TrackingResultList


_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "yolo11n.pt"
_RUN_REAL_MODEL_SMOKE = os.environ.get("EVILEYE_RUN_MODEL_PROCESS_SMOKE") == "1"


@pytest.mark.skipif(
    not _RUN_REAL_MODEL_SMOKE or not _MODEL_PATH.is_file(),
    reason="set EVILEYE_RUN_MODEL_PROCESS_SMOKE=1 and provide models/yolo11n.pt",
)
def test_attribute_classifier_runs_real_model_in_spawn_worker():
    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.zeros((64, 64, 3), dtype=np.uint8), frame_id=1, timestamp=1.0
    )
    adapter = EvilEyeBase.create_instance("AttributeClassifier")
    adapter.set_params(
        module_id="AttributeClassifier",
        execution_mode="process",
        source_ids=[0],
        enabled=True,
        model=str(_MODEL_PATH),
        attrs=["person"],
        inference_size=64,
        conf_threshold=0.25,
    )
    try:
        assert adapter.init() is True
        adapter.start()
        tracking = TrackingResultList()
        tracking.source_id = 0
        tracking.frame_id = 1
        tracking.roi_data = [{"track_id": 101, "roi_bbox": [0, 0, 64, 64]}]
        frame = Frame()
        frame.source_id = 0
        frame.frame_id = 1
        frame.frame_handle = handle
        adapter.put((tracking, frame))

        deadline = time.monotonic() + 90
        output = None
        while time.monotonic() < deadline:
            output = adapter.get()
            if output is not None:
                break
            if adapter.degraded:
                raise AssertionError("AttributeClassifier worker degraded")
            time.sleep(0.05)

        assert output is not None, adapter.get_debug_info({})
        assert output[0].attr_results[101]["person"]["detected_now"] is False
        assert output[1].frame_handle == handle
        assert owner.get_frame_view(handle)[0, 0, 0] == 0
    finally:
        adapter.stop()
        adapter.release()
        owner.release_frame(handle)


_HARDHAT_MODEL_PATH = Path(__file__).resolve().parents[3] / "models" / "y8mhardhats.pt"


@pytest.mark.skipif(
    not _RUN_REAL_MODEL_SMOKE or not _HARDHAT_MODEL_PATH.is_file(),
    reason="set EVILEYE_RUN_MODEL_PROCESS_SMOKE=1 and provide models/y8mhardhats.pt",
)
def test_attribute_detector_runs_real_model_in_spawn_worker():
    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.zeros((64, 64, 3), dtype=np.uint8), frame_id=2, timestamp=2.0
    )
    adapter = EvilEyeBase.create_instance("AttributeDetector")
    adapter.set_params(
        module_id="AttributeDetector",
        execution_mode="process",
        source_ids=[0],
        enabled=True,
        model=str(_HARDHAT_MODEL_PATH),
        attrs=["hard_hat", "no_hard_hat"],
        class_mapping={"hard_hat": 0, "no_hard_hat": 1},
        confidence_thresholds={"hard_hat": 0.4, "no_hard_hat": 0.4},
        conf=0.1,
        inference_size=64,
        roi=[[]],
    )
    try:
        assert adapter.init() is True
        adapter.start()
        frame = Frame()
        frame.source_id = 0
        frame.frame_id = 2
        frame.frame_handle = handle
        adapter.put(frame)

        deadline = time.monotonic() + 90
        output = None
        while time.monotonic() < deadline:
            output = adapter.get()
            if output is not None:
                break
            if adapter.degraded:
                raise AssertionError("AttributeDetector worker degraded")
            time.sleep(0.05)

        assert output is not None, adapter.get_debug_info({})
        assert output[0].source_id == 0
        assert output[0].frame_id == 2
        assert adapter.get_model_class_mapping() == {"hard_hat": 0, "no_hard_hat": 1}
        assert output[1].frame_handle == handle
        assert owner.get_frame_view(handle)[0, 0, 0] == 0
    finally:
        adapter.stop()
        adapter.release()
        owner.release_frame(handle)
