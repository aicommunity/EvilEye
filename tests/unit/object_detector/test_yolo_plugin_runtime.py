from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from evileye.core.frame import Frame
from evileye.core.plugins import ModuleRuntimeContext
from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_detector.object_detection_yolo import ObjectDetectorYolo
from evileye.object_detector.object_detection_rtdetr import ObjectDetectorRtdetr
from evileye.object_detector.object_detection_rfdetr import ObjectDetectorRfdetr


class _FakeBox:
    def __init__(self, class_id, confidence, bbox):
        self.cls = np.asarray([class_id])
        self.conf = np.asarray([confidence])
        self.xyxy = np.asarray([bbox], dtype=float)


class _FakeBoxes:
    def __init__(self, items):
        self.items = items

    def cpu(self):
        return self

    def numpy(self):
        return self

    @property
    def xyxy(self):
        return np.concatenate([item.xyxy for item in self.items], axis=0)

    @property
    def conf(self):
        return np.concatenate([item.conf for item in self.items], axis=0)

    @property
    def cls(self):
        return np.concatenate([item.cls for item in self.items], axis=0)


class _FakeYoloRuntime:
    predictions = []
    calls = []

    def __init__(self, logger=None):
        self.model = None
        self.classes = []

    def configure(self, model, classes, params):
        self.model_name = model
        self.params = params

    def load(self):
        self.model = SimpleNamespace(names={0: "person", 1: "car"})

    def predict_raw(self, images, **kwargs):
        type(self).calls.append((images, kwargs))
        classes = kwargs.get("classes")
        predictions = type(self).predictions
        if classes is not None:
            predictions = [box for box in predictions if int(box.cls[0]) in classes]
        return [
            SimpleNamespace(boxes=_FakeBoxes(predictions))
            for _ in images
        ]

    def release(self):
        self.model = None


def _frame():
    frame = Frame()
    frame.source_id = 4
    frame.frame_id = 11
    frame.time_stamp = 2.5
    frame.image = np.zeros((60, 80, 3), dtype=np.uint8)
    return frame


def test_yolo_plugin_item_maps_roi_detections_and_class_names(monkeypatch):
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    _FakeYoloRuntime.calls = []
    _FakeYoloRuntime.predictions = [
        _FakeBox(0, 0.82, [1, 2, 5, 6]),
        _FakeBox(1, 0.95, [2, 3, 8, 9]),
    ]
    module = ObjectDetectorYolo()
    state = module.create_state(
        {
            "model": "synthetic.pt",
            "classes": ["person"],
            "conf": 0.3,
            "inference_size": 128,
            "source_ids": [4],
            "roi": [[[10, 20, 30, 25]]],
        },
        ModuleRuntimeContext("evileye/ObjectDetectorYolo", "thread", (4,)),
    )

    result, output_frame = module.process_item(_frame(), state)

    assert isinstance(result, DetectionResultList)
    assert output_frame.frame_id == 11
    assert (result.source_id, result.frame_id, result.time_stamp) == (4, 11, 2.5)
    assert len(result.detections) == 1
    assert result.detections[0].class_id == 0
    assert result.detections[0].bounding_box == [11, 22, 15, 26]
    assert module.get_model_class_mapping() == {"person": 0, "car": 1}
    assert _FakeYoloRuntime.calls[0][0][0].shape == (25, 30, 3)
    assert _FakeYoloRuntime.calls[0][1]["classes"] == [0]
    module.close()


def test_yolo_plugin_rejects_names_missing_from_model_mapping(monkeypatch):
    import pytest
    import evileye.object_detector.yolo_runtime as yolo_runtime_module

    monkeypatch.setattr(yolo_runtime_module, "YoloRuntime", _FakeYoloRuntime)
    module = ObjectDetectorYolo()

    with pytest.raises(ValueError, match="absent from model mapping"):
        module.create_state({"classes": ["helmet"]})
    module.close()


def test_rtdetr_plugin_uses_shared_item_contract(monkeypatch):
    import evileye.object_detector.rtdetr_runtime as rtdetr_runtime_module

    monkeypatch.setattr(rtdetr_runtime_module, "RtdetrRuntime", _FakeYoloRuntime)
    _FakeYoloRuntime.calls = []
    _FakeYoloRuntime.predictions = [_FakeBox(0, 0.82, [1, 2, 5, 6])]
    module = ObjectDetectorRtdetr()
    state = module.create_state(
        {
            "model": "synthetic-rtdetr.pt",
            "classes": ["person"],
            "source_ids": [4],
            "roi": [[[10, 20, 30, 25]]],
        },
        ModuleRuntimeContext(
            "evileye/ObjectDetectorRtdetr", "thread", (4,), worker_count=1
        ),
    )

    result, output_frame = module.process_item(_frame(), state)

    assert module.model_name == "synthetic-rtdetr.pt"
    assert isinstance(result, DetectionResultList)
    assert output_frame.frame_id == 11
    assert len(result.detections) == 1
    assert result.detections[0].bounding_box == [11, 22, 15, 26]
    module.close()


class _FakeRfdetrRuntime:
    def __init__(self, logger=None):
        self.model = None
        self.images = None

    def configure(self, model, classes, params):
        self.model_name = model
        self.params = params

    def load(self):
        self.model = SimpleNamespace(class_names=["person", "car"])

    def predict_raw(self, images, **kwargs):
        self.images = images
        return [
            SimpleNamespace(
                xyxy=np.asarray([[1, 2, 5, 6], [2, 3, 8, 9]], dtype=float),
                confidence=np.asarray([0.82, 0.95]),
                class_id=np.asarray([0, 1]),
            )
            for _ in images
        ]

    def release(self):
        self.model = None


def test_rfdetr_plugin_uses_native_results_and_shared_item_contract(monkeypatch):
    import evileye.object_detector.rfdetr_runtime as rfdetr_runtime_module

    monkeypatch.setattr(rfdetr_runtime_module, "RfdetrRuntime", _FakeRfdetrRuntime)
    module = ObjectDetectorRfdetr()
    state = module.create_state(
        {
            "model": "rfdetr-nano",
            "classes": ["person"],
            "conf": 0.3,
            "source_ids": [4],
            "roi": [[[10, 20, 30, 25]]],
        },
        ModuleRuntimeContext("evileye/ObjectDetectorRfdetr", "thread", (4,)),
    )

    result, output_frame = module.process_item(_frame(), state)

    assert result.source_id == 4
    assert result.frame_id == 11
    assert output_frame.frame_id == 11
    assert module.get_model_class_mapping() == {"person": 0, "car": 1}
    assert len(result.detections) == 1
    assert result.detections[0].class_id == 0
    assert result.detections[0].bounding_box == [11, 22, 15, 26]
    assert module._plugin_model_runtime.images[0].shape == (25, 30, 3)
    module.close()
