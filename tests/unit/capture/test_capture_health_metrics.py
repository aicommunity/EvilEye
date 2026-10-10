from datetime import datetime, timedelta

from evileye.capture.video_capture_base import VideoCaptureBase


class _CaptureForHealth(VideoCaptureBase):
    def default(self):
        pass

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def get_frames_impl(self):
        return []

    def _grab_frames(self):
        pass

    def _retrieve_frames(self):
        pass



def test_capture_health_counters_persist_after_event_queues_are_drained():
    capture = _CaptureForHealth()
    start = datetime(2026, 10, 10, 12, 0, 0)
    capture._record_disconnect(start)
    capture._record_reconnect(start + timedelta(seconds=4))

    assert len(capture.get_disconnects_info()) == 1
    assert len(capture.get_reconnects_info()) == 1
    assert len(capture.get_disconnects_info()) == 0
    assert len(capture.get_reconnects_info()) == 0

    health = capture.get_capture_health()
    assert health["disconnect_count"] == 1
    assert health["reconnect_count"] == 1
    assert health["last_transition"] == {
        "kind": "reconnect",
        "timestamp": "2026-10-10T12:00:04",
    }
