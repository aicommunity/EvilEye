import datetime
from queue import Queue

from evileye.core.frame import Frame
from evileye.object_detector.object_detection_base import DetectionResultList
from evileye.object_tracker.object_tracking_base import (
    ObjectTrackingBase,
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
    det, frame = _det_frame()
    detections = [det, frame]
    tracker._emit_mp_tracker_result(detections, None)
    got = tracker.queue_out.get_nowait()
    assert got[0].tracks == []
    assert got[1] is frame


def test_mp_put_fail_records_dropped_id():
    tracker = _MpTrackerStub()
    tracker.queue_dropped_id = Queue()

    class _Bridge:
        def enqueue(self, _packed, _job):
            return False

    tracker._mp_control = object()
    tracker._bridge = _Bridge()
    det, frame = _det_frame()
    assert tracker._enqueue_mp_tracker_job([det, frame], {"packed": True}, None) is False
    assert tracker.queue_dropped_id.get_nowait() == [1, 10]
