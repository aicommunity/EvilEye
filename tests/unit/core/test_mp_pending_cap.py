"""Tests for MP pending FIFO cap helpers."""

from collections import deque

import pytest

from evileye.core import mp_queue_config as qc
from evileye.object_detector.detection_thread_yolo_mp import DetectionThreadYoloMp


class _CapHarness:
    """Minimal harness mirroring DetectionThreadYoloMp pending cap."""

    def __init__(self, cap: int):
        self._mp_pending: deque = deque()
        self._mp_pending_cap = cap
        self._diag_mp_pending_evict = 0
        self._released = 0

    def _release_handles(self, handles) -> None:
        self._released += len(handles or [])

    def _enforce_pending_cap(self) -> None:
        while len(self._mp_pending) >= self._mp_pending_cap:
            _, _, handles = self._mp_pending.popleft()
            self._release_handles(handles)
            self._diag_mp_pending_evict += 1

    def enqueue(self, n: int) -> None:
        for i in range(n):
            self._enforce_pending_cap()
            self._mp_pending.append(([], None, [f"h{i}"]))


@pytest.mark.unit
def test_mp_pending_cap_detector_default():
    assert qc.mp_pending_cap_detector(1) == 2
    assert qc.mp_pending_cap_detector(3) == 3


@pytest.mark.unit
def test_mp_pending_cap_detector_env(monkeypatch):
    monkeypatch.setenv("EVILEYE_MP_PENDING_CAP", "6")
    assert qc.mp_pending_cap_detector(1) == 6


@pytest.mark.unit
def test_enforce_pending_cap_evicts_oldest():
    h = _CapHarness(cap=2)
    h.enqueue(4)
    assert len(h._mp_pending) == 2
    assert h._diag_mp_pending_evict == 2
    assert h._released == 2


@pytest.mark.unit
def test_detection_thread_yolo_mp_has_bridge_and_reporter():
    """Smoke: MP thread uses MpAsyncBridge and MpPendingReporter API."""
    assert hasattr(DetectionThreadYoloMp, "mp_pending_depth")
    assert hasattr(DetectionThreadYoloMp, "_bridge")
