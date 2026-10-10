from __future__ import annotations

import logging
import threading
import time
from types import SimpleNamespace

from evileye.controller.controller import Controller
from evileye.core.class_manager import ClassManager


class _Detector:
    module_id = "vendor/helmet-detector"
    execution_mode = "process"
    reports_model_class_mapping = True

    def get_model_class_mapping(self):
        return {"helmet": 0, "person": 1}


class _Pipeline:
    def __init__(self, detector):
        self._detector = detector

    def get_detectors(self):
        return [self._detector]


def test_controller_merges_late_process_plugin_class_mapping(monkeypatch):
    detector = _Detector()
    controller = object.__new__(Controller)
    controller.pipeline = _Pipeline(detector)
    controller.class_manager = ClassManager()
    controller._detector_class_mapping_cache = {}
    controller.class_mapping = {}
    controller.visualizer = SimpleNamespace(class_mapping={})
    controller.logger = logging.getLogger("test.plugin_class_mapping")
    controller.model_loading_timeout_sec = 2

    class _InlineThread:
        def __init__(self, *, target, daemon):
            self._target = target

        def start(self):
            self._target()

    monkeypatch.setattr(threading, "Thread", _InlineThread)
    monkeypatch.setattr(time, "sleep", lambda _seconds: None)

    controller._schedule_periodic_class_update()

    expected = {"helmet": 0, "person": 1}
    assert controller.class_mapping == expected
    assert controller.visualizer.class_mapping == expected
    assert len(controller.class_manager.sources) == 1


def test_controller_uses_pipeline_detector_accessor():
    detector = _Detector()
    controller = object.__new__(Controller)
    controller.pipeline = _Pipeline(detector)

    assert controller._get_pipeline_detectors() == [detector]

    controller.pipeline = SimpleNamespace(processors=[object()])
    assert controller._get_pipeline_detectors() == []


def test_controller_allows_detector_without_class_mapping_provider():
    assert Controller._get_detector_class_mapping(object()) is None
