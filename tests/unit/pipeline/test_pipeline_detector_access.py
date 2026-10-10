from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest

from evileye.pipelines import pipeline_surveillance as pipeline_module
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def test_detector_accessor_uses_authoritative_detector_list():
    pipeline = object.__new__(PipelineSurveillance)
    detector = object()
    pipeline.detectors = [detector]
    pipeline.processors = [
        SimpleNamespace(processor_name="detectors", processors=[object()])
    ]

    assert pipeline.get_detectors() == [detector]
    assert pipeline.get_detector_by_index(0) is detector
    assert pipeline.get_detector_by_index(1) is None


def test_detector_accessor_does_not_recover_from_processor_list():
    pipeline = object.__new__(PipelineSurveillance)
    pipeline.detectors = []
    pipeline.processors = [
        SimpleNamespace(processor_name="detectors", processors=[object()])
    ]

    assert pipeline.get_detectors() == []


def test_detector_initialization_propagates_broken_processor_state(monkeypatch):
    class BrokenProcessorStep:
        def __init__(self, **_kwargs):
            self.processor_name = "detectors"

        def set_params(self, _params):
            pass

        def init(self):
            pass

        @property
        def processors(self):
            raise RuntimeError("processor state unavailable")

    pipeline = object.__new__(PipelineSurveillance)
    pipeline.logger = logging.getLogger("test.pipeline_detector_access")
    pipeline._add_processor = lambda _processor: None
    monkeypatch.setattr(pipeline_module, "ProcessorStep", BrokenProcessorStep)

    with pytest.raises(RuntimeError, match="processor state unavailable"):
        pipeline._init_detectors([{"type": "ObjectDetectorYolo"}])
