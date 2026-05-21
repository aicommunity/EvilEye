"""Process-mode capture: one frame per source_id per tick."""
from queue import Queue

from evileye.capture.video_capture_base import VideoCaptureBase
from evileye.core.frame import CaptureImage


class _CaptureStub(VideoCaptureBase):
    def get_frames_impl(self):
        return []

    def _grab_frames(self):
        pass

    def _retrieve_frames(self):
        pass

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def start(self):
        pass

    def stop(self):
        pass

    def default(self):
        pass

    def reset_impl(self):
        pass


def _img(source_id: int, frame_id: int) -> CaptureImage:
    img = CaptureImage()
    img.source_id = source_id
    img.frame_id = frame_id
    return img


def test_get_frames_from_queue_one_per_source_id():
    cap = _CaptureStub()
    cap.frames_queue = Queue(maxsize=16)
    cap.capture_config.queue_size = 4
    cap.frames_queue.put(_img(1, 10))
    cap.frames_queue.put(_img(2, 20))
    cap.frames_queue.put(_img(1, 11))

    out = cap._get_frames_from_queue()
    sids = sorted(f.source_id for f in out)
    assert sids == [1, 2]
    assert out[0].frame_id == 10
    assert out[1].frame_id == 20

    # Deferred cam1 frame remains for next tick
    again = cap._get_frames_from_queue()
    assert len(again) == 1
    assert again[0].source_id == 1
    assert again[0].frame_id == 11
