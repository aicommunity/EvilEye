"""Capture worker must not nest multiprocessing (daemon cannot spawn children)."""

from multiprocessing import Event

from evileye.capture.mp_worker_capture import MpWorkerCapture
from evileye.capture.video_capture_base import VideoCaptureBase
from evileye.core.processor_base import EXEC_MODE_THREAD


def test_mp_worker_capture_init_worker_forces_thread_mode():
    worker = MpWorkerCapture(None, None, stop_event=Event())
    worker.set_params(
        {
            "camera": "x.mp4",
            "execution_mode": "process",
            "type": "VideoCaptureGStreamer",
        }
    )
    seen = {}

    def fake_init(capture, params):
        seen["execution_mode"] = params.get("execution_mode")
        return False

    worker._create_capture = lambda use_gstreamer: object()  # noqa: ARG005
    worker._init_capture_instance = fake_init
    worker.init_worker()
    assert seen["execution_mode"] == EXEC_MODE_THREAD


def test_video_capture_skips_nested_process_mode_in_mp_child(monkeypatch):
    monkeypatch.setattr(
        VideoCaptureBase,
        "_running_inside_mp_worker",
        staticmethod(lambda: True),
    )

    class DummyCapture(VideoCaptureBase):
        def init_impl(self):
            self.is_inited = True
            return True

        def get_frames_impl(self):
            return []

        def _grab_frames(self):
            pass

        def _retrieve_frames(self):
            pass

        def default(self):
            pass

        def reset_impl(self):
            pass

        def release_impl(self):
            pass

        def set_params_impl(self):
            pass

        def get_params_impl(self):
            return {}

        def start_impl(self):
            pass

        def stop_impl(self):
            pass

    cap = DummyCapture()
    cap.execution_mode = "process"

    def fail_nested():
        raise AssertionError("must not spawn nested MpControl")

    cap._init_process_mode = fail_nested
    assert cap.init() is True
