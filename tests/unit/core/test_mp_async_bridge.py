"""Unit tests for MpAsyncBridge pending FIFO and release_on_drop."""

from __future__ import annotations

import queue
from unittest.mock import MagicMock

import pytest

from evileye.core.mp_async_bridge import MpAsyncBridge
from evileye.core.mp_pending_jobs import DetectorPendingJob


class _FakeMpControl:
    def __init__(self, *, fail_puts: int = 0, input_maxsize: int = 64):
        self.input_queue = queue.Queue(maxsize=input_maxsize)
        self._fail_puts = fail_puts
        self._put_count = 0

    def put_nowait(self, data: object) -> None:
        self._put_count += 1
        if self._put_count <= self._fail_puts:
            raise queue.Full
        if self.input_queue.full():
            raise queue.Full
        self.input_queue.put_nowait(data)


def test_fifo_pop_head():
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl()
    bridge = MpAsyncBridge(
        pending_cap=0,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    j1 = DetectorPendingJob([], "cap1", [])
    j2 = DetectorPendingJob([], "cap2", [])
    assert bridge.enqueue("p1", j1) is True
    assert bridge.enqueue("p2", j2) is True
    assert bridge.pop_head() is j1
    assert bridge.pop_head() is j2
    assert bridge.pop_head() is None
    assert released == []


def test_cap_evict_calls_release_on_drop():
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl()
    bridge = MpAsyncBridge(
        pending_cap=2,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    for i in range(3):
        job = DetectorPendingJob([], f"cap{i}", [])
        assert bridge.enqueue(f"p{i}", job) is True
    assert bridge.diag_pending_evict() == 1
    assert released == ["cap0"]
    assert bridge.depth() == 2
    # FIFO parity: queue depth must match pending after cap-evict.
    assert ctrl.input_queue.qsize() == bridge.depth()
    assert list(ctrl.input_queue.queue) == ["p1", "p2"]


def test_cap_evict_queue_depth_matches_pending():
    """Regression C1: 3 enqueue / cap=2 → queue depth == pending depth."""
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl()
    bridge = MpAsyncBridge(
        pending_cap=2,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    for i in range(3):
        assert bridge.enqueue(f"p{i}", DetectorPendingJob([], f"cap{i}", [])) is True
    assert ctrl.input_queue.qsize() == bridge.depth() == 2
    assert "cap0" in released
    # Released handle must not remain readable by a worker.
    assert "p0" not in list(ctrl.input_queue.queue)


def test_put_dropped_releases_job():
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl(fail_puts=99)
    bridge = MpAsyncBridge(
        pending_cap=0,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    job = DetectorPendingJob([], "dropped", [])
    assert bridge.enqueue("payload", job) is False
    assert bridge.diag_put_dropped() == 1
    assert "dropped" in released


def test_clear_releases_all():
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl()
    bridge = MpAsyncBridge(
        pending_cap=0,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    bridge.enqueue("p1", DetectorPendingJob([], "a", []))
    bridge.enqueue("p2", DetectorPendingJob([], "b", []))
    bridge.clear()
    assert bridge.depth() == 0
    assert set(released) == {"a", "b"}


def test_overflow_evict_keeps_queue_pending_parity():
    released: list[str] = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    ctrl = _FakeMpControl(input_maxsize=2)
    bridge = MpAsyncBridge(
        pending_cap=0,
        mp_control=ctrl,
        release_on_drop=release,
        logger=MagicMock(),
    )
    assert bridge.enqueue("p0", DetectorPendingJob([], "cap0", [])) is True
    assert bridge.enqueue("p1", DetectorPendingJob([], "cap1", [])) is True
    # Third put hits Full → drop queue head + pending head, then accept p2.
    assert bridge.enqueue("p2", DetectorPendingJob([], "cap2", [])) is True
    assert bridge.depth() == 2
    assert ctrl.input_queue.qsize() == 2
    assert list(ctrl.input_queue.queue) == ["p1", "p2"]
    assert "cap0" in released
