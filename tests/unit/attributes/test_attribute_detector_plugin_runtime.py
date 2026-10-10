from __future__ import annotations

import time
from types import SimpleNamespace

import numpy as np
import pytest

from evileye.attributes_detection.attribute_detector import AttributeDetector
from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.frame_transport import SharedFrameTransport
from evileye.core.plugin_runtime import ItemModuleAdapter
from evileye.core.plugins import ModuleRuntimeContext
from evileye.core.plugins import plugin_registry
from evileye.object_detector.object_detection_base import DetectionResultList


class _FakeBox:
    def __init__(self, class_id, confidence, bbox):
        self.cls = np.asarray([class_id])
        self.conf = np.asarray([confidence])
        self.xyxy = np.asarray([bbox], dtype=float)


class _FakeBoxes:
    def __init__(self, boxes):
        self.items = boxes

    def cpu(self):
        return self

    def numpy(self):
        return self

    def __iter__(self):
        return iter(self.items)


class _FakeYoloRuntime:
    predictions = []
    calls = []

    def __init__(self, logger=None):
        self.model = None

    def configure(self, model, classes, params):
        self.classes = classes
        self.params = params

    def load(self):
        self.model = object()

    def predict_raw(self, images, **kwargs):
        type(self).calls.append((images, kwargs))
        return [SimpleNamespace(boxes=_FakeBoxes(type(self).predictions))]

    def release(self):
        self.model = None


def _frame(source_id=2, frame_id=7):
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.time_stamp = 1.25
    frame.image = np.zeros((60, 80, 3), dtype=np.uint8)
    return frame


def test_attribute_detector_maps_roi_boxes_and_class_thresholds(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    _FakeYoloRuntime.calls = []
    _FakeYoloRuntime.predictions = [
        _FakeBox(0, 0.65, [1, 2, 5, 6]),
        _FakeBox(1, 0.45, [3, 4, 9, 10]),
    ]
    module = AttributeDetector()
    state = module.create_state(
        {
            "model": "hardhat.pt",
            "attrs": ["hard_hat", "no_hard_hat"],
            "class_mapping": {"hard_hat": 0, "no_hard_hat": 1},
            "confidence_thresholds": {"hard_hat": 0.4, "no_hard_hat": 0.5},
            "conf": 0.1,
            "inference_size": 128,
            "source_ids": [2],
            "roi": [[[10, 20, 40, 30]]],
        }
    )
    frame = _frame()

    result, output_frame = module.process_item(frame, state)

    assert isinstance(result, DetectionResultList)
    assert output_frame is frame
    assert (result.source_id, result.frame_id, result.time_stamp) == (2, 7, 1.25)
    assert len(result.detections) == 1
    detection = result.detections[0]
    assert detection.class_id == 0
    assert detection.detection_data["attribute"] == "hard_hat"
    assert detection.bounding_box == [11, 22, 15, 26]
    assert _FakeYoloRuntime.calls[0][0][0].shape == (30, 40, 3)
    assert _FakeYoloRuntime.calls[0][1]["classes"] == [0, 1]
    assert module.get_model_class_mapping() == {"hard_hat": 0, "no_hard_hat": 1}
    module.close()


def test_attribute_detector_reads_shared_frame_without_consuming_handle(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    _FakeYoloRuntime.calls = []
    _FakeYoloRuntime.predictions = []
    owner = SharedFrameTransport()
    handle = owner.alloc_frame(
        np.full((10, 12, 3), 5, dtype=np.uint8), frame_id=7, timestamp=1.25
    )
    module = AttributeDetector()
    state = module.create_state({"attrs": ["hard_hat"]})
    frame = Frame()
    frame.source_id = 2
    frame.frame_id = 7
    frame.frame_handle = handle

    try:
        result, output_frame = module.process_item(frame, state)
        assert not result.detections
        assert output_frame.frame_handle == handle
        assert _FakeYoloRuntime.calls[0][0][0][0, 0, 0] == 5
        assert owner.get_frame_view(handle)[0, 0, 0] == 5
    finally:
        module.close()
        owner.release_frame(handle)


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_attribute_detector_uses_item_runtime(execution_mode):
    registered = plugin_registry.get_module("AttributeDetector")
    assert registered is not None
    assert registered.spec.kind == "processor_item"
    assert "legacy_processor_protocol" not in registered.spec.capabilities

    adapter = EvilEyeBase.create_instance("AttributeDetector")
    assert isinstance(adapter, ItemModuleAdapter)
    adapter.set_params(
        module_id="AttributeDetector",
        execution_mode=execution_mode,
        source_ids=[3],
        enabled=False,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        frame = _frame(source_id=3, frame_id=9)
        adapter.put(frame)
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        output = None
        while output is None and time.monotonic() < deadline:
            output = adapter.get()
            if output is None:
                time.sleep(0.01)
        assert output is not None
        assert isinstance(output[0], DetectionResultList)
        assert output[0].source_id == 3
        assert output[0].frame_id == 9
        assert output[1].frame_id == 9
    finally:
        adapter.stop()
        adapter.release()


def test_attribute_detector_preserves_stride_with_empty_intermediate_results(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    _FakeYoloRuntime.calls = []
    _FakeYoloRuntime.predictions = [_FakeBox(0, 0.65, [1, 2, 5, 6])]
    module = AttributeDetector()
    state = module.create_state({"attrs": ["hard_hat"], "vid_stride": 2})

    first, _ = module.process_item(_frame(frame_id=1), state)
    skipped, _ = module.process_item(_frame(frame_id=2), state)
    third, _ = module.process_item(_frame(frame_id=3), state)

    assert len(first.detections) == 1
    assert not skipped.detections
    assert len(third.detections) == 1
    assert len(_FakeYoloRuntime.calls) == 2
    module.close()


def test_attribute_detector_rejects_unsupported_worker_count(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    module = AttributeDetector()

    with pytest.raises(ValueError, match="num_detection_threads must be 1"):
        module.create_state({"enabled": False, "num_detection_threads": 3})


def test_attribute_detector_uses_runtime_source_ids_for_roi_selection(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    module = AttributeDetector()
    state = module.create_state(
        {"enabled": False, "roi": [[[0, 0, 10, 10]], [[10, 10, 20, 20]]]},
        ModuleRuntimeContext("evileye/AttributeDetector", "thread", (2, 5)),
    )
    frame = _frame(source_id=5)

    assert module._rois_for_frame(frame, frame.image) == [(10, 10, 20, 20)]
    assert state == {"frame_counts": {}}
    module.close()
