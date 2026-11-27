"""VideoThread must keep the source index the visualizer passes in."""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    import PyQt6  # noqa: F401
except ImportError:
    pytest.importorskip("PyQt5")


def test_explicit_thread_num_is_not_overwritten(qapp):
    if qapp is None:
        pytest.skip("Qt application is unavailable")
    from evileye.visualization_modules.video_thread import VideoThread

    previous = VideoThread.thread_counter
    try:
        first = VideoThread(1, 5, 1, 1, False, None, thread_num=0)
        second = VideoThread(2, 5, 1, 1, False, None, thread_num=1)
        assert first.thread_num == 0
        assert second.thread_num == 1
        assert VideoThread.thread_counter == previous
    finally:
        VideoThread.thread_counter = previous


def test_missing_thread_num_uses_class_counter(qapp):
    if qapp is None:
        pytest.skip("Qt application is unavailable")
    from evileye.visualization_modules.video_thread import VideoThread

    previous = VideoThread.thread_counter
    VideoThread.thread_counter = 4
    try:
        thread = VideoThread(3, 5, 1, 1, False, None)
        assert thread.thread_num == 4
        assert VideoThread.thread_counter == 5
    finally:
        VideoThread.thread_counter = previous
