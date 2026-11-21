import logging

import pytest

from evileye.core.pipeline_processors import PipelineProcessors
from evileye.core.processor_step import ProcessorStep
from evileye.core.processor_source import ProcessorSource


class _ReadinessProbe:
    module_id = "tests.readiness/detector"

    def __init__(self, ready):
        self.ready = ready
        self.received_timeout = None

    def is_ready(self, timeout):
        self.received_timeout = timeout
        return self.ready


class _DetectorStep(ProcessorStep):
    def __init__(self, detector):
        self.processor_name = "detectors"
        self.processors = [detector]
        self.logger = logging.getLogger("tests.pipeline-readiness")
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True


class _Source(ProcessorSource):
    def __init__(self):
        self.started = False
        self.stopped = False

    def start(self):
        self.started = True

    def stop(self):
        self.stopped = True

    def process(self, data=None):
        return data


def _pipeline_with_detector(ready):
    detector = _ReadinessProbe(ready)
    step = _DetectorStep(detector)
    source = _Source()
    pipeline = PipelineProcessors()
    pipeline.processors = [step, source]
    return pipeline, detector, step, source


def test_sources_start_only_after_frame_workers_are_ready(monkeypatch):
    monkeypatch.setenv("EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC", "1")
    pipeline, detector, step, source = _pipeline_with_detector(True)

    pipeline.start()
    try:
        assert detector.received_timeout == 1.0
        assert step.started is True
        assert source.started is True
    finally:
        pipeline.stop()


def test_unready_frame_worker_fails_start_without_starting_sources(monkeypatch):
    monkeypatch.setenv("EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC", "0.1")
    pipeline, _detector, step, source = _pipeline_with_detector(False)

    with pytest.raises(RuntimeError, match="sources were not started.*tests.readiness/detector"):
        pipeline.start()

    assert step.started is True
    assert step.stopped is True
    assert source.started is False
    assert source.stopped is True


def test_non_positive_readiness_timeout_fails_before_starting_processors(monkeypatch):
    monkeypatch.setenv("EVILEYE_FRAME_WORKER_READY_TIMEOUT_SEC", "0")
    pipeline, _detector, step, source = _pipeline_with_detector(True)

    with pytest.raises(RuntimeError, match="must be a positive number"):
        pipeline.start()

    assert step.started is False
    assert source.started is False
