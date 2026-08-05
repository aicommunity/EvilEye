from types import SimpleNamespace
from multiprocessing import Event

from evileye.capture.mp_worker_capture import MpWorkerCapture


class _FakeLogger:
    def __init__(self):
        self.infos = []
        self.errors = []
        self.warnings = []

    def info(self, msg, *args):
        self.infos.append(msg % args if args else msg)

    def error(self, msg, *args):
        self.errors.append(msg % args if args else msg)

    def warning(self, msg, *args):
        self.warnings.append(msg % args if args else msg)

    def debug(self, msg, *args):
        pass


def test_log_recording_status_accepts_gst_continuous_recorder():
    worker = MpWorkerCapture(None, None, stop_event=Event())
    worker.logger = _FakeLogger()
    worker._capture_params = {"source_names": ["Cam1"], "camera": "rtsp://x"}

    gst_rec = SimpleNamespace(is_running=True, _refs=object())
    capture = SimpleNamespace(
        recording_params=SimpleNamespace(
            enabled=True,
            continuous_recording_enabled=True,
            out_dir="/tmp",
        ),
        recorder_manager=None,
        _gst_continuous_recorder=gst_rec,
    )
    worker._log_recording_status(capture)
    assert not worker.logger.errors
    assert any("backend=gstreamer" in m for m in worker.logger.infos)


def test_log_recording_status_errors_when_no_recorder():
    worker = MpWorkerCapture(None, None, stop_event=Event())
    worker.logger = _FakeLogger()
    worker._capture_params = {"source_names": ["Cam1"]}
    capture = SimpleNamespace(
        recording_params=SimpleNamespace(
            enabled=True,
            continuous_recording_enabled=True,
            out_dir="/tmp",
        ),
        recorder_manager=None,
        _gst_continuous_recorder=None,
    )
    worker._log_recording_status(capture)
    assert worker.logger.errors
