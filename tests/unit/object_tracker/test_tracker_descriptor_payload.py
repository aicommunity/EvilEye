import numpy as np

from evileye.object_tracker.object_tracking_base import ObjectTrackingBase
from evileye.object_tracker.mp_worker_tracker import MpWorkerTracker


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


class _FrameLike:
    def __init__(self):
        self.source_id = 7
        self.frame_id = 42
        self.time_stamp = 1.25
        self.current_video_frame = 42
        self.current_video_position = 1250.0
        self.source_video_duration = 5000.0
        self.image = np.zeros((16, 24, 3), dtype=np.uint8)


def test_tracker_pack_and_worker_unpack_descriptor_payload_roundtrip():
    tracker = _DummyTracker()
    detection_result = {"source_id": 7, "frame_id": 42, "detections": []}
    frame = _FrameLike()

    packed, handle = tracker._pack_for_worker((detection_result, frame))
    assert isinstance(packed, dict)
    assert handle is not None

    worker = MpWorkerTracker(input_queue=None, output_queue=None)
    unpacked_det, unpacked_frame = worker._unpack_input(packed)

    assert unpacked_det == detection_result
    assert unpacked_frame.source_id == 7
    assert unpacked_frame.frame_id == 42
    assert unpacked_frame.image is not None
    assert unpacked_frame.image.shape == (16, 24, 3)

    tracker._frame_transport.release_frame(handle)
