"""Tests for detector vid_stride consumption."""

from queue import Queue

from evileye.object_detector.detection_thread_base import DetectionThreadBase


class _StrideProbe(DetectionThreadBase):
    def init_detection_implementation(self):
        return None

    def _run_prediction(self, images, batch_size):
        return None

    def get_bboxes(self, result, roi):
        return [], [], []


def test_consume_stride_slot_stride_1_always_true():
    th = _StrideProbe(1, [], [0], [[]], {}, Queue())
    assert [th.consume_stride_slot() for _ in range(5)] == [True] * 5


def test_consume_stride_slot_stride_2_alternates():
    th = _StrideProbe(2, [], [0], [[]], {}, Queue())
    assert [th.consume_stride_slot() for _ in range(6)] == [True, False, True, False, True, False]


def test_consume_stride_slot_stride_3_pattern():
    th = _StrideProbe(3, [], [0], [[]], {}, Queue())
    assert [th.consume_stride_slot() for _ in range(6)] == [True, False, False, True, False, False]
