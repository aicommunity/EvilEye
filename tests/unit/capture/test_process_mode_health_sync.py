"""Process-mode parent proxy health sync for runtime snapshot / web API."""

import time

from evileye.capture.constants import CaptureConstants
from evileye.capture.video_capture_base import CaptureDeviceType, VideoCaptureBase
from evileye.core.processor_base import EXEC_MODE_PROCESS


class _StubCapture(VideoCaptureBase):
    def default(self):
        return None

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        return True

    def get_frames_impl(self):
        return []

    def _grab_frames(self):
        pass

    def _retrieve_frames(self):
        pass


class _AliveMpControl:
    def is_alive(self) -> bool:
        return True


class _DeadMpControl:
    def is_alive(self) -> bool:
        return False


def _process_capture() -> _StubCapture:
    cap = _StubCapture()
    cap.execution_mode = EXEC_MODE_PROCESS
    cap.source_type = CaptureDeviceType.IpCamera
    cap.is_inited = True
    cap._mp_control = _AliveMpControl()
    return cap


def test_sync_optimistic_during_init_grace(monkeypatch):
    cap = _process_capture()
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cap._mp_worker_started_mono = now
    cap._mp_last_frame_mono = 0.0
    cap.sync_process_mode_health()
    assert cap.is_working is True


def test_sync_no_frames_after_grace_marks_ip_camera_down(monkeypatch):
    cap = _process_capture()
    now = 1000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cap._mp_worker_started_mono = now - CaptureConstants.INIT_GRACE_PERIOD_SECONDS - 1.0
    cap._mp_last_frame_mono = 0.0
    cap.sync_process_mode_health()
    assert cap.is_working is False


def test_sync_recent_frame_marks_working(monkeypatch):
    cap = _process_capture()
    now = 2000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cap._mp_last_frame_mono = now - 1.0
    cap.sync_process_mode_health()
    assert cap.is_working is True


def test_sync_stale_frame_marks_ip_camera_down(monkeypatch):
    cap = _process_capture()
    now = 3000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cap._mp_last_frame_mono = now - CaptureConstants.FRAME_TIMEOUT_SECONDS - 1.0
    cap.sync_process_mode_health()
    assert cap.is_working is False


def test_touch_process_mode_frame_activity(monkeypatch):
    cap = _process_capture()
    now = 4000.0
    monkeypatch.setattr(time, "monotonic", lambda: now)
    cap.is_working = False
    cap._touch_process_mode_frame_activity()
    assert cap.is_working is True
    assert cap._mp_last_frame_mono == now
    assert cap.last_frame_time is not None


def test_dead_worker_marks_not_working():
    cap = _process_capture()
    cap._mp_control = _DeadMpControl()
    cap.is_working = True
    cap.sync_process_mode_health()
    assert cap.is_working is False
