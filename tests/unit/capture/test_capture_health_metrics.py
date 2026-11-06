from datetime import datetime, timedelta

import numpy as np

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


def test_capture_frame_carries_connection_generation():
    capture = _CaptureForHealth()
    capture._reconnect_count = 3

    frame = capture._create_capture_image(
        image=np.zeros((2, 2, 3), dtype=np.uint8),
        frame_id=7,
        timestamp=123.0,
        source_id=4,
    )

    assert frame.connection_generation == 3


def test_process_capture_ipc_preserves_connection_generation():
    import multiprocessing as mp
    import queue

    from evileye.capture.mp_worker_capture import MpWorkerCapture
    from evileye.core.frame import Frame

    worker = MpWorkerCapture(
        queue.Queue(), queue.Queue(), stop_event=mp.get_context("spawn").Event()
    )
    capture = _CaptureForHealth()
    capture._frame_transport = worker._frame_transport
    frame = Frame()
    frame.image = np.zeros((2, 2, 3), dtype=np.uint8)
    frame.frame_id = 8
    frame.connection_generation = 4

    packed = worker._pack_frame_for_ipc(frame)
    try:
        unpacked = capture._unpack_capture_payload(packed)
        assert unpacked.connection_generation == 4
        assert unpacked.frame_id == 8
    finally:
        worker._frame_transport.release_frame(packed["frame_handle"])
        worker._frame_transport.release_all_owned()
