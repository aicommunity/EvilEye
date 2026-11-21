import numpy as np

from evileye.object_tracker.object_tracking_base import ObjectTrackingBase
from evileye.object_tracker.mp_worker_tracker import MpWorkerTracker
from evileye.core.frame import Frame
from evileye.core.mp_context import get_spawn_context


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


def test_tracker_pack_and_worker_unpack_descriptor_payload_roundtrip():
    tracker = _DummyTracker()
    detection_result = {"source_id": 7, "frame_id": 42, "detections": []}
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = 42
    frame.time_stamp = 1.25
    frame.current_video_frame = 42
    frame.current_video_position = 1250.0
    frame.source_video_duration = 5000.0
    frame.image = np.zeros((16, 24, 3), dtype=np.uint8)

    packed, handle = tracker._pack_for_worker((detection_result, frame))
    assert isinstance(packed, dict)
    assert handle is not None

    worker = MpWorkerTracker(
        input_queue=None,
        output_queue=None,
        stop_event=get_spawn_context().Event(),
    )
    unpacked_det, unpacked_frame = worker._unpack_input(packed)

    assert unpacked_det == detection_result
    assert unpacked_frame.source_id == 7
    assert unpacked_frame.frame_id == 42
    assert unpacked_frame.image is not None
    assert unpacked_frame.image.shape == (16, 24, 3)

    tracker._frame_transport.release_frame(handle)
