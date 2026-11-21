from evileye.capture.video_capture_base import VideoCaptureBase
from evileye.core.frame import Frame


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


def _frame(source_id, frame_id, generation):
    frame = Frame()
    frame.source_id = source_id
    frame.frame_id = frame_id
    frame.connection_generation = generation
    return frame


def test_source_read_emits_each_source_frame_once_and_accepts_new_generation():
    capture = _DummyCapture()
    capture._plugin_source_opened = True
    capture.is_inited = True
    batches = [
        [_frame(3, 1, 0), _frame(4, 1, 0)],
        [_frame(3, 1, 0)],  # A latest-frame backend may return the same frame again.
        [_frame(3, 1, 1)],  # A reconnect may reset frame_id in a new generation.
    ]
    capture.get = lambda: batches.pop(0) if batches else []

    first = capture.read()
    second = capture.read()
    after_reconnect = capture.read()

    assert (first.source_id, first.frame_id, first.connection_generation) == (3, 1, 0)
    assert (second.source_id, second.frame_id, second.connection_generation) == (4, 1, 0)
    assert (after_reconnect.source_id, after_reconnect.frame_id, after_reconnect.connection_generation) == (3, 1, 1)



def test_source_read_stops_after_repeated_latest_frame_at_eof():
    capture = _DummyCapture()
    capture._plugin_source_opened = True
    capture.is_inited = True
    capture.finished = True
    latest = _frame(3, 5, 0)
    capture.get = lambda: [latest]

    assert capture.read() is latest
    assert capture.read() is None



def test_source_read_rejects_frames_without_identity():
    import pytest

    capture = _DummyCapture()
    capture._plugin_source_opened = True
    capture.is_inited = True
    invalid = Frame()
    invalid.source_id = 3
    capture.get = lambda: [invalid]

    with pytest.raises(ValueError, match="source_id and frame_id"):
        capture.read()
