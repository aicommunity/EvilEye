"""MP YOLO detection thread: feed/drain async contract."""
from collections import deque
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from evileye.capture.video_capture_base import CaptureImage
from evileye.object_detector.detection_thread_yolo_mp import DetectionThreadYoloMp


@pytest.mark.unit
def test_yolo_mp_uses_feed_drain_threads_not_base_processing():
    thread = DetectionThreadYoloMp(
        "model.pt",
        1,
        [],
        [0],
        [[]],
        {},
        True,
        set(),
        Queue(),
    )
    assert thread.processing_thread is None
    assert thread._mp_feed_thread is not None
    assert thread._mp_drain_thread is not None
    thread.stop()


@pytest.mark.unit
def test_enqueue_mp_det_job_fifo_pending():
    thread = DetectionThreadYoloMp(
        "model.pt",
        1,
        [],
        [0],
        [[]],
        {},
        True,
        set(),
        Queue(),
    )
    mock_control = MagicMock()
    mock_control.put_nowait = MagicMock()
    mock_control.input_queue = __import__("queue").Queue()
    thread.mp_control = mock_control
    if thread._bridge is not None:
        thread._bridge._mp_control = mock_control
        thread._bridge._input_queue = mock_control.input_queue
    img = CaptureImage()
    img.source_id = 0
    img.frame_id = 1
    split = [[img, [0, 0]]]
    thread._enqueue_mp_det_job(split, img, ["h1"], [])
    mock_control.put_nowait.assert_called_once_with(["h1"])
    assert thread.mp_pending_depth() == 1
    if thread._bridge is not None:
        thread._bridge.clear()
    thread.mp_control = None
    thread.stop()


@pytest.mark.unit
def test_detection_result_from_predict_empty():
    thread = DetectionThreadYoloMp(
        "model.pt",
        1,
        [],
        [0],
        [[]],
        {},
        True,
        set(),
        Queue(),
    )
    img = CaptureImage()
    img.source_id = 2
    img.frame_id = 10
    split = [[img, [0, 0]]]
    out = thread._detection_result_from_predict(split, [])
    assert out is not None
    assert out.source_id == 2
    assert out.frame_id == 10
    assert out.detections == []
    thread.stop()
