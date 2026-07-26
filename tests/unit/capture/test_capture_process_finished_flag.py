from evileye.capture.video_capture_base import VideoCaptureBase


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


class _DeadMpControl:
    def is_alive(self):
        return False

    def output_empty(self):
        return True


def test_mark_finished_if_worker_stopped_sets_finished_flag():
    cap = _DummyCapture()
    cap.finished = False
    cap._mp_control = _DeadMpControl()
    cap._mark_finished_if_worker_stopped()
    assert cap.finished is True
