from queue import Queue

from evileye.object_detector.object_detection_base import ObjectDetectorBase, EXEC_MODE_PROCESS


class _DummyDetector(ObjectDetectorBase):
    def _get_detection_thread_type(self):
        return "dummy"

    def _get_default_model_name(self):
        return "dummy.pt"


def test_detector_uses_thread_queues_in_process_mode():
    det = _DummyDetector()
    det.execution_mode = EXEC_MODE_PROCESS
    det._init_queues()
    assert isinstance(det.queue_in, Queue)
    assert isinstance(det.queue_out, Queue)
    assert isinstance(det.queue_dropped_id, Queue)
