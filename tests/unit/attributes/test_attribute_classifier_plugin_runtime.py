from __future__ import annotations

import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugin_runtime import ItemModuleAdapter
from evileye.core.plugins import plugin_registry
from evileye.attributes_detection.attribute_classifier import AttributeClassifier
from evileye.object_tracker.tracking_results import TrackingResultList


class _FakeYoloRuntime:
    def __init__(self, logger=None):
        self.model = None
        self.config = None

    def configure(self, model, classes, params):
        self.config = (model, classes, params)

    def load(self):
        self.model = object()

    def release(self):
        self.model = None


def _frame(source_id=0, frame_id=1):
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.image = np.zeros((10, 12, 3), dtype=np.uint8)
    return frame


def test_attribute_classifier_process_item_preserves_roi_and_track_identity(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    module = AttributeClassifier()
    state = module.create_state(
        {
            "model": "helmet.pt",
            "attrs": ["helmet"],
            "class_mapping": {"helmet": 2},
            "conf_threshold": 0.7,
            "inference_size": 128,
        }
    )
    observed_shapes = []
    module._classify_roi_with_detector = lambda image: (
        observed_shapes.append(image.shape)
        or {"helmet": {"detected_now": True, "confidence": 0.91}}
    )
    tracking_data = TrackingResultList()
    tracking_data.roi_data = [{"track_id": 42, "roi_bbox": [2, 3, 7, 8]}]
    frame = _frame()

    output_data, output_frame = module.process_item((tracking_data, frame), state)

    assert output_data is tracking_data
    assert output_frame is frame
    assert observed_shapes == [(5, 5, 3)]
    assert tracking_data.attr_results[42]["helmet"]["detected_now"] is True
    assert module.attr_class_mapping == {2: "helmet"}
    module.close()


def test_attribute_classifier_reads_shared_frame_without_consuming_handle(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module
    from evileye.core.frame_transport import SharedFrameTransport

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.full((10, 12, 3), 5, dtype=np.uint8), frame_id=1, timestamp=1.0
    )
    module = AttributeClassifier()
    state = module.create_state({"attrs": ["helmet"]})
    module._classify_roi_with_detector = lambda image: {
        "shape": list(image.shape),
        "pixel": int(image[0, 0, 0]),
    }
    tracking_data = TrackingResultList()
    tracking_data.roi_data = [{"track_id": 7, "roi_bbox": [0, 0, 4, 4]}]
    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 1
    frame.frame_handle = handle

    try:
        module.process_item((tracking_data, frame), state)
        assert tracking_data.attr_results[7]["pixel"] == 5
        assert owner.get_frame_view(handle)[0, 0, 0] == 5
    finally:
        module.close()
        owner.release_frame(handle)


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_attribute_classifier_plugin_uses_item_runtime(execution_mode):
    registered = plugin_registry.get_module("AttributeClassifier")
    assert registered is not None
    assert registered.spec.kind == "processor_item"

    adapter = EvilEyeBase.create_instance("AttributeClassifier")
    assert isinstance(adapter, ItemModuleAdapter)
    adapter.set_params(
        module_id="AttributeClassifier",
        execution_mode=execution_mode,
        source_ids=[3],
        enabled=False,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        tracking_data = TrackingResultList()
        tracking_data.source_id = 3
        tracking_data.frame_id = 9
        frame = _frame(3, 9)
        adapter.put((tracking_data, frame))

        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.01)

        assert output is not None
        assert output[0].source_id == 3
        assert output[0].frame_id == 9
        assert output[1].frame_id == 9
    finally:
        adapter.stop()
        adapter.release()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_attribute_classifier_runtime_preserves_shared_frame_handle(execution_mode):
    from evileye.core.frame_transport import SharedFrameTransport

    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.full((10, 12, 3), 6, dtype=np.uint8), frame_id=9, timestamp=2.0
    )
    adapter = EvilEyeBase.create_instance("AttributeClassifier")
    adapter.set_params(
        module_id="AttributeClassifier",
        execution_mode=execution_mode,
        source_ids=[3],
        enabled=False,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        tracking_data = TrackingResultList()
        tracking_data.source_id = 3
        tracking_data.frame_id = 9
        frame = Frame()
        frame.source_id = 3
        frame.frame_id = 9
        frame.frame_handle = handle
        adapter.put((tracking_data, frame))

        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.01)

        assert output is not None
        assert output[1].frame_handle == handle
        assert owner.get_frame_view(handle)[0, 0, 0] == 6
    finally:
        adapter.stop()
        adapter.release()
        owner.release_frame(handle)
