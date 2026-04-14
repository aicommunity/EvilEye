from queue import Queue

from evileye.object_tracker.object_tracking_base import (
    ObjectTrackingBase,
    EXEC_MODE_PROCESS,
)


class _DummyTracker(ObjectTrackingBase):
    def _process_impl(self):
        return None

    def set_params_impl(self):
        return None

    def get_params_impl(self):
        return {}

    def init_impl(self, **kwargs):
        return None

    def release_impl(self):
        return None

    def reset_impl(self):
        return None

    def default(self):
        return None


def test_tracker_uses_thread_queues_in_process_mode():
    tracker = _DummyTracker()
    tracker.execution_mode = EXEC_MODE_PROCESS
    tracker._init_queues()
    assert isinstance(tracker.queue_in, Queue)
    assert isinstance(tracker.queue_out, Queue)
    assert isinstance(tracker.queue_dropped_id, Queue)
