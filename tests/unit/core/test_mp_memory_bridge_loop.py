"""MEM-3 lightweight: bridge clear/enqueue cycle does not grow pending depth."""

from unittest.mock import MagicMock
from queue import Queue

import pytest

from evileye.core.mp_async_bridge import MpAsyncBridge
from evileye.core.mp_pending_jobs import DetectorPendingJob


class _Ctrl:
    def __init__(self):
        self.input_queue = Queue()

    def put_nowait(self, data):
        self.input_queue.put_nowait(data)


@pytest.mark.unit
def test_bridge_enqueue_clear_cycle_stable_depth():
    released = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    control = _Ctrl()
    bridge = MpAsyncBridge(
        pending_cap=4,
        mp_control=control,
        release_on_drop=release,
        logger=MagicMock(),
    )
    for i in range(200):
        job = DetectorPendingJob([], f"j{i}", [])
        bridge.enqueue([f"p{i}"], job)
        if i % 3 == 0:
            control.input_queue.get_nowait()
            bridge.pop_head()
        if i % 17 == 0:
            while not control.input_queue.empty():
                control.input_queue.get_nowait()
            bridge.clear()
        assert bridge.depth() <= 4
    while not control.input_queue.empty():
        control.input_queue.get_nowait()
    bridge.clear()
    assert bridge.depth() == 0
