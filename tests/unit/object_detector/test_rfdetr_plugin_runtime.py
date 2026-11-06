from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import numpy as np
import pytest

from evileye.object_detector.rfdetr_runtime import RfdetrRuntime


class _FakeDetections:
    def __init__(self, class_id=0):
        self.xyxy = np.asarray([[1, 2, 5, 6]], dtype=float)
        self.confidence = np.asarray([0.8], dtype=float)
        self.class_id = np.asarray([class_id], dtype=int)


class _FakeModel:
    resolutions = []
    thresholds = []

    def __init__(self, resolution):
        type(self).resolutions.append(resolution)

    def optimize_for_inference(self):
        return None

    def predict(self, images, threshold):
        type(self).thresholds.append(threshold)
        return [_FakeDetections() for _ in images]


def _fake_rfdetr_module():
    module = ModuleType("rfdetr")
    for name in ("Nano", "Small", "Medium", "Large"):
        setattr(module, f"RFDETR{name}", _FakeModel)
    return module


def test_rfdetr_runtime_uses_named_variant_and_preserves_batch_results(monkeypatch):
    monkeypatch.setitem(sys.modules, "rfdetr", _fake_rfdetr_module())
    _FakeModel.resolutions = []
    _FakeModel.thresholds = []
    runtime = RfdetrRuntime()
    runtime.configure("rfdetr-small", [], {"imgsz": 512, "conf": 0.42})
    runtime.load()

    images = [np.zeros((32, 32, 3)), np.ones((32, 32, 3))]
    results = runtime.predict_raw(images)

    assert _FakeModel.resolutions == [512]
    assert _FakeModel.thresholds == [0.42]
    assert len(results) == 2
    assert all(isinstance(result, _FakeDetections) for result in results)
    runtime.release()
    assert runtime.model is None


def test_rfdetr_runtime_rejects_unknown_model_without_defaulting(monkeypatch):
    monkeypatch.setitem(sys.modules, "rfdetr", _fake_rfdetr_module())
    runtime = RfdetrRuntime()
    runtime.configure("rfdetr-custom", [], {})

    with pytest.raises(ValueError, match="Unsupported RF-DETR model"):
        runtime.load()


def test_rfdetr_runtime_rejects_ambiguous_batch_result(monkeypatch):
    monkeypatch.setitem(sys.modules, "rfdetr", _fake_rfdetr_module())
    runtime = RfdetrRuntime()
    runtime.configure("nano", [], {})
    runtime.model = SimpleNamespace(
        predict=lambda images, threshold: _FakeDetections()
    )

    with pytest.raises(RuntimeError, match="one result per image"):
        runtime.predict_raw([np.zeros((32, 32, 3)), np.ones((32, 32, 3))])
