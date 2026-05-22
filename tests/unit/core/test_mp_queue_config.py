"""Tests for MP queue sizing helpers."""

import os

import pytest

from evileye.core import mp_queue_config as qc


@pytest.mark.unit
def test_env_scale_default():
    old = os.environ.pop("EVILEYE_MP_QUEUE_SCALE", None)
    try:
        assert qc.env_scale() == 1
        assert qc.detector_input_queue_size() == 10
    finally:
        if old is not None:
            os.environ["EVILEYE_MP_QUEUE_SCALE"] = old


@pytest.mark.unit
def test_env_scale_doubles_queues(monkeypatch):
    monkeypatch.setenv("EVILEYE_MP_QUEUE_SCALE", "2")
    assert qc.detector_thread_queue_size() >= 4
    assert qc.mp_control_queue_size(3, role="detector") >= 6


@pytest.mark.unit
def test_mp_drain_poll_sec_env(monkeypatch):
    monkeypatch.setenv("EVILEYE_MP_DRAIN_POLL_SEC", "0.01")
    assert qc.mp_drain_poll_sec() == 0.01


@pytest.mark.unit
def test_mp_pending_cap_tracker_default():
    assert qc.mp_pending_cap_tracker() == 4


@pytest.mark.unit
def test_mp_pending_cap_tracker_env(monkeypatch):
    monkeypatch.setenv("EVILEYE_MP_PENDING_CAP_TRACKER", "8")
    assert qc.mp_pending_cap_tracker() == 8
