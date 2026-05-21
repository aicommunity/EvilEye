"""Guards for YOLO init thread/process boundaries."""

import threading
import time
from queue import Queue
from unittest.mock import MagicMock, patch

import pytest

from evileye.object_detector.detection_thread_yolo import DetectionThreadYolo
from evileye.object_detector.detection_thread_yolo_mp import DetectionThreadYoloMp


@pytest.mark.unit
def test_detection_thread_yolo_mp_init_detection_is_noop():
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
    thread.init_detection_implementation()
    assert thread.model is None
    thread.stop()


@pytest.mark.unit
def test_detection_thread_yolo_loads_in_processing_thread():
    init_tid_holder = []
    load_tid_holder = []

    class _FakeYOLO:
        def __init__(self, *args, **kwargs):
            load_tid_holder.append(threading.get_ident())

        def fuse(self):
            pass

        def half(self):
            pass

        @property
        def names(self):
            return {0: "a"}

    queue_out = Queue()
    thread = DetectionThreadYolo(
        "model.pt", 1, [], [0], [[]], {"half": False}, queue_out
    )
    with patch("evileye.object_detector.detection_thread_yolo.YOLO", _FakeYOLO):
        thread.start()
        time.sleep(0.5)
        thread.stop()

    assert load_tid_holder
    assert load_tid_holder[0] == thread.processing_thread.ident


@pytest.mark.unit
def test_detection_thread_yolo_stop_clears_model():
    queue_out = Queue()
    thread = DetectionThreadYolo(
        "missing-model.pt", 1, [], [0], [[]], {"half": False}, queue_out
    )
    with patch("evileye.object_detector.detection_thread_yolo.YOLO", side_effect=RuntimeError("no model")):
        thread.init_detection_implementation()
    assert thread.model is None
    thread.model = MagicMock()
    thread.stop()
    assert thread.model is None
