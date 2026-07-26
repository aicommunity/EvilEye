"""Tests for adaptive PIPELINE_SYNC_MP in ProcessorStep."""

import os
from unittest.mock import patch

import pytest

from evileye.core.processor_step import ProcessorStep


def _make_step() -> ProcessorStep:
    return ProcessorStep(
        processor_name="detectors",
        class_name="ObjectDetectorYolo",
        num_processors=1,
        order=1,
    )


@pytest.mark.unit
def test_sync_mp_adaptive_mode_detected(monkeypatch):
    monkeypatch.setenv("EVILEYE_PIPELINE_SYNC_MP", "adaptive")
    step = _make_step()
    assert step._sync_mp_adaptive() is True
    assert step._sync_mp_enabled() is True


@pytest.mark.unit
def test_sync_mp_adaptive_skips_wait_when_pending_high(monkeypatch):
    monkeypatch.setenv("EVILEYE_PIPELINE_SYNC_MP", "adaptive")
    monkeypatch.setenv("EVILEYE_SYNC_MP_PENDING_MAX", "10")
    step = _make_step()
    step._mp_pending_snapshot = 15
    step.processors = []
    with patch.object(step, "_drain_processor_outputs", return_value=0) as drain:
        added = step._sync_mp_drain_after_put([])
    assert added == 0
    drain.assert_not_called()


@pytest.mark.unit
def test_sync_mp_full_mode_always_runs(monkeypatch):
    monkeypatch.setenv("EVILEYE_PIPELINE_SYNC_MP", "1")
    monkeypatch.setenv("EVILEYE_PIPELINE_SYNC_MP_MS", "1")
    step = _make_step()
    step._mp_pending_snapshot = 99
    proc = type("P", (), {"execution_mode": "process", "get": lambda self: None})()
    step.processors = [proc]
    with patch.object(step, "_drain_processor_outputs", return_value=1) as drain:
        added = step._sync_mp_drain_after_put([])
    assert added >= 1
    drain.assert_called()


@pytest.mark.unit
def test_drain_max_items_from_env(monkeypatch):
    monkeypatch.setenv("EVILEYE_MP_DRAIN_MAX_ITEMS", "128")
    step = _make_step()
    assert step._drain_max_items() == 128
