"""Regression: detection threads must not raise on shutdown after model release."""

from queue import Queue
from unittest.mock import MagicMock, patch

from evileye.object_detector.detection_thread_yolo import DetectionThreadYolo


def test_yolo_init_safe_when_model_attr_removed_on_shutdown():
    q = Queue()
    thread = DetectionThreadYolo(
        "models/yolov8n.pt", 1, [0], [0], [[]], {}, q, logger_name="test"
    )
    thread.run_flag = False
    if hasattr(thread, "model"):
        del thread.model
    thread.init_detection_implementation()


@patch("evileye.object_detector.detection_thread_yolo.YOLO")
def test_yolo_init_uses_getattr_when_model_attr_missing(mock_yolo):
    mock_yolo.return_value = MagicMock(names={0: "person"})
    q = Queue()
    thread = DetectionThreadYolo(
        "models/yolov8n.pt", 1, [0], [0], [[]], {}, q, logger_name="test2"
    )
    thread.run_flag = True
    if hasattr(thread, "model"):
        del thread.model
    thread.init_detection_implementation()
    assert thread.model is mock_yolo.return_value


def test_yolo_stop_releases_model_after_worker_join():
    q = Queue()
    thread = DetectionThreadYolo(
        "models/yolov8n.pt", 1, [0], [0], [[]], {}, q, logger_name="test3"
    )
    thread.model = MagicMock()
    thread.run_flag = True
    thread.processing_thread = MagicMock()
    thread.processing_thread.is_alive.return_value = False

    thread.stop()

    assert thread.model is None
