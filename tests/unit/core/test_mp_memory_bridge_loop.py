"""MEM-3 lightweight: bridge clear/enqueue cycle does not grow pending depth."""

from unittest.mock import MagicMock

import pytest

from evileye.core.mp_async_bridge import MpAsyncBridge
from evileye.core.mp_pending_jobs import DetectorPendingJob


class _Ctrl:
    input_queue = __import__("queue").Queue()

    def put_nowait(self, _):
        pass


@pytest.mark.unit
def test_bridge_enqueue_clear_cycle_stable_depth():
    released = []

    def release(job: DetectorPendingJob) -> None:
        released.append(job.capture_image)

    bridge = MpAsyncBridge(
        pending_cap=4,
        mp_control=_Ctrl(),
        release_on_drop=release,
        logger=MagicMock(),
    )
    for i in range(200):
        job = DetectorPendingJob([], f"j{i}", [])
        bridge.enqueue([f"p{i}"], job)
        if i % 3 == 0:
            bridge.pop_head()
        if i % 17 == 0:
            bridge.clear()
    assert bridge.depth() == 0
