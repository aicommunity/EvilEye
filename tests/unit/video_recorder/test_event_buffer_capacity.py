"""Tests for EventBuffer capacity bounding."""

import os

import numpy as np
import pytest

from evileye.video_recorder.event_buffer import EventBuffer


@pytest.mark.unit
def test_event_buffer_always_has_maxlen_when_fps_none(monkeypatch):
    monkeypatch.delenv("EVILEYE_EVENT_BUFFER_FPS_MAX", raising=False)
    buf = EventBuffer(max_duration_seconds=25.0, fps=None)
    assert buf.buffer.maxlen is not None
    assert buf.buffer.maxlen == int(5.0 * 25.0 * 1.2)


@pytest.mark.unit
def test_event_buffer_respects_fps():
    buf = EventBuffer(max_duration_seconds=10.0, fps=2.0)
    assert buf.buffer.maxlen == int(2.0 * 10.0 * 1.2)
    frame = np.zeros((4, 4, 3), dtype=np.uint8)
    for i in range(50):
        buf.add_frame(frame, timestamp=float(i))
    assert len(buf.buffer) <= buf.buffer.maxlen
