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


def test_capture_unpack_descriptor_payload_preserves_frame_contract():
    cap = _DummyCapture()
    transport = SharedFrameTransport()
    arr = np.full((8, 12, 3), 9, dtype=np.uint8)
    handle = transport.alloc_frame(arr, frame_id=77, timestamp=1.5)
    payload = {
        "frame_handle": handle,
        "frame_meta": {
            "source_id": 3,
            "frame_id": 77,
            "connection_generation": 2,
            "current_video_frame": 71,
            "current_video_position": 2840.0,
            "source_video_duration": 8.0,
            "time_stamp": 1.5,
            "pts_ns": 2_900_000_000,
            "media_pts_sec": 1.4,
        },
    }
    try:
        frame = cap._unpack_capture_payload(payload)
        assert frame is not None
        assert frame.source_id == 3
        assert frame.frame_id == 77
        assert frame.connection_generation == 2
        assert frame.current_video_frame == 71
        assert frame.current_video_position == 2840.0
        assert frame.source_video_duration == 8.0
        assert frame.time_stamp == 1.5
        assert frame.pts_ns == 2_900_000_000
        assert frame.media_pts_sec == 1.4
        assert frame.image.shape == (8, 12, 3)
        assert frame.image.dtype == np.uint8
        assert frame.image.flags.c_contiguous
        assert np.all(frame.image == 9)
    finally:
        transport.release_frame(handle)
