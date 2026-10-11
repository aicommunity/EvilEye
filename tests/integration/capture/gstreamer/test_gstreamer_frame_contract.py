from __future__ import annotations

import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import Frame
from evileye.core.plugin_runtime import SourceModuleAdapter


@pytest.mark.usefixtures("ensure_gst_initialized")
def test_gstreamer_source_emits_documented_frame_and_pts_contract(
    test_video_mp4,
    monkeypatch,
):
    pytest.importorskip("gi")
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

    source = EvilEyeBase.create_instance("VideoCaptureGStreamer")
    assert isinstance(source, SourceModuleAdapter)

    def disable_main_loop(self, *args, **kwargs):
        return None

    monkeypatch.setattr(VideoCaptureGStreamer, "_start_main_loop", disable_main_loop)
    monkeypatch.setattr(VideoCaptureGStreamer, "_stop_main_loop", disable_main_loop)
    source.set_params(
        module_id="VideoCaptureGStreamer",
        execution_mode="thread",
        source="VideoFile",
        camera=test_video_mp4,
        source_ids=[23],
        source_names=["frame-contract"],
        desired_fps=15,
        loop_play=False,
        force_sw_decoder=True,
    )
    assert source.init() is True
    source.start()

    frames = []
    deadline = time.monotonic() + 12
    try:
        while time.monotonic() < deadline and len(frames) < 8:
            frames.extend(source.get())
            if len(frames) < 8:
                time.sleep(0.02)
    finally:
        source.stop()
        source.release()

    assert len(frames) >= 8
    assert all(isinstance(frame, Frame) for frame in frames)
    assert {frame.source_id for frame in frames} == {23}
    frame_ids = [frame.frame_id for frame in frames]
    assert frame_ids == sorted(set(frame_ids))
    assert all(frame.connection_generation == 0 for frame in frames)
    assert all(frame.image.shape == (240, 320, 3) for frame in frames)
    assert all(frame.image.dtype == np.uint8 for frame in frames)
    assert all(frame.image.flags.c_contiguous for frame in frames)

    pts = [frame.pts_ns for frame in frames if frame.pts_ns is not None]
    media_pts = [frame.media_pts_sec for frame in frames if frame.media_pts_sec is not None]
    assert len(pts) >= 3
    assert len(media_pts) == len(pts)
    assert pts == sorted(pts)
    assert media_pts == sorted(media_pts)
    assert media_pts[0] == pytest.approx(0.0, abs=0.01)
    assert 0.05 <= media_pts[1] - media_pts[0] <= 0.09


@pytest.mark.usefixtures("ensure_gst_initialized")
def test_gstreamer_source_advances_generation_after_file_loop(
    test_video_mp4,
):
    pytest.importorskip("gi")
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

    source = EvilEyeBase.create_instance("VideoCaptureGStreamer")
    assert isinstance(source, SourceModuleAdapter)
    source.set_params(
        module_id="VideoCaptureGStreamer",
        execution_mode="thread",
        source="VideoFile",
        camera=test_video_mp4,
        source_ids=[24],
        source_names=["frame-generation"],
        desired_fps=15,
        loop_play=True,
        force_sw_decoder=True,
    )
    assert source.init() is True
    source.start()

    frames = []
    deadline = time.monotonic() + 18
    try:
        while time.monotonic() < deadline:
            frames.extend(source.get())
            by_generation = {}
            for frame in frames:
                by_generation.setdefault(frame.connection_generation, []).append(frame)
            if len(by_generation.get(0, [])) >= 3 and len(by_generation.get(1, [])) >= 3:
                break
            time.sleep(0.02)
    finally:
        source.stop()
        source.release()

    generations = {frame.connection_generation for frame in frames}
    assert 0 in generations
    assert 1 in generations
    for generation in (0, 1):
        generation_frames = [
            frame for frame in frames if frame.connection_generation == generation
        ]
        frame_ids = [frame.frame_id for frame in generation_frames]
        assert frame_ids == sorted(set(frame_ids))
        media_pts = [
            frame.media_pts_sec
            for frame in generation_frames
            if frame.media_pts_sec is not None
        ]
        assert media_pts
        assert media_pts[0] == pytest.approx(0.0, abs=0.01)
