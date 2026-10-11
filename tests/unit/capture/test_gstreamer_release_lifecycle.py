from threading import Event, Lock, Thread
from types import SimpleNamespace
from unittest.mock import Mock

from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer


def _capture():
    return SimpleNamespace(
        _release_lock=Lock(),
        _teardown_pipeline=Mock(),
        logger=Mock(),
        source_names=["camera-test"],
        is_inited=True,
        is_working=True,
    )


def test_release_uses_shared_pipeline_teardown_and_resets_health():
    capture = _capture()

    VideoCaptureGStreamer.release(capture)

    capture._teardown_pipeline.assert_called_once_with("release", join_main_loop=True)
    assert capture.is_inited is False
    assert capture.is_working is False
    assert capture._release_lock.acquire(blocking=False)
    capture._release_lock.release()


def test_release_waits_for_concurrent_teardown_to_finish():
    capture = _capture()
    capture._release_lock.acquire()
    started = Event()
    finished = Event()

    def release_capture():
        started.set()
        VideoCaptureGStreamer.release(capture)
        finished.set()

    worker = Thread(target=release_capture)
    worker.start()
    try:
        assert started.wait(timeout=1.0)
        assert not finished.wait(timeout=0.05)
        capture._teardown_pipeline.assert_not_called()
    finally:
        capture._release_lock.release()

    worker.join(timeout=1.0)
    assert not worker.is_alive()
    assert finished.is_set()
    capture._teardown_pipeline.assert_called_once_with("release", join_main_loop=True)


def test_release_releases_lifecycle_lock_when_teardown_fails():
    capture = _capture()
    capture._teardown_pipeline.side_effect = RuntimeError("teardown failed")

    VideoCaptureGStreamer.release(capture)

    capture.logger.error.assert_called_once()
    assert capture._release_lock.acquire(blocking=False)
    capture._release_lock.release()
