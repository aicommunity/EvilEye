import numpy as np

from evileye.capture.video_capture_base import VideoCaptureBase
from evileye.core.frame_transport import SharedFrameTransport


class _DummyCapture(VideoCaptureBase):
    def set_params_impl(self):
        return None

    def get_params_impl(self):
        return {}

    def init_impl(self):
        return True

    def release_impl(self):
        return None

    def reset_impl(self):
        return None

    def default(self):
        return None

    def get_frames_impl(self):
        return []

    def _grab_frames(self):
        return None

    def _retrieve_frames(self):
        return None


def test_capture_unpack_descriptor_payload_sets_frame_handle():
    cap = _DummyCapture()
    transport = SharedFrameTransport()
    arr = np.zeros((8, 12, 3), dtype=np.uint8)
    handle = transport.alloc_frame(arr, frame_id=77, timestamp=1.5)
    payload = {
        "frame_handle": handle,
        "frame_meta": {
            "source_id": 3,
            "frame_id": 77,
            "time_stamp": 1.5,
        },
    }
    frame = cap._unpack_capture_payload(payload)
    assert frame is not None
    assert frame.image is not None
    assert frame.source_id == 3
    assert frame.frame_id == 77
    assert frame.image.shape == (8, 12, 3)
