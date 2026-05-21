import datetime
from queue import Empty, Full, Queue

from evileye.core.frame import Frame
from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_tracker.object_tracking_base import (
    ObjectTrackingBase,
    _MP_GET_MAX_ROUNDS,
    _MP_GET_TIMEOUT_SEC,
    _empty_tracking_output_for_input,
)


class _MpTrackerStub(ObjectTrackingBase):
    def _process_impl(self):
        pass

    def init_impl(self, **kwargs):
        return True

    def default(self):
        self.params.clear()

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def reset_impl(self):
        pass


def _det_frame(source_id=1, frame_id=10):
    det = DetectionResultList()
    det.source_id = source_id
    det.frame_id = frame_id
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.time_stamp = datetime.datetime.now()
    return det, frame


def test_empty_tracking_output_for_input():
    det, frame = _det_frame()
    tracks_info, out_frame = _empty_tracking_output_for_input(det, frame)
    assert tracks_info.source_id == 1
    assert tracks_info.frame_id == 10
    assert tracks_info.tracks == []
    assert out_frame is frame


def test_mp_get_timeout_emits_empty():
    tracker = _MpTrackerStub()
    tracker.queue_out = Queue(maxsize=4)

    class _MpControl:
        def put_nowait(self, _packed):
            return None

        def get(self, timeout=None):
            raise Empty()

    tracker._mp_control = _MpControl()
    det, frame = _det_frame()
    detections = [det, frame]
    tracker._pack_for_worker = lambda d: (d, None)
    tracker._mp_control.put_nowait(detections)

    result = None
    for _ in range(_MP_GET_MAX_ROUNDS):
        try:
            result = tracker._mp_control.get(timeout=_MP_GET_TIMEOUT_SEC)
            break
        except Empty:
            continue
    assert result is None
    tracker._put_out_drop_oldest(_empty_tracking_output_for_input(det, frame))
    got = tracker.queue_out.get_nowait()
    assert got[0].tracks == []
    assert got[1] is frame


def test_mp_put_fail_records_dropped_id():
    tracker = _MpTrackerStub()
    tracker.queue_dropped_id = Queue()

    class _MpControl:
        def put_nowait(self, _packed):
            raise Full()

    tracker._mp_control = _MpControl()
    _, frame = _det_frame()
    tracker.queue_dropped_id.put_nowait([frame.source_id, frame.frame_id])

    dropped = []
    while not tracker.queue_dropped_id.empty():
        dropped.append(tracker.queue_dropped_id.get_nowait())
    assert dropped == [[1, 10]]
