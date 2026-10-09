from __future__ import annotations

import time

import numpy as np
import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.frame import CaptureImage
from evileye.core.plugin_runtime import SourceModuleAdapter
from evileye.capture.video_capture_opencv import VideoCaptureOpencv


def test_opencv_builtin_source_uses_spi_adapter_with_thread_capture_backend(tmp_path):
    cv2 = pytest.importorskip("cv2")
    video_path = tmp_path / "spi-source.avi"
    writer = cv2.VideoWriter(
        str(video_path), cv2.VideoWriter_fourcc(*"MJPG"), 5.0, (64, 48)
    )
    if not writer.isOpened():
        pytest.skip("OpenCV video writer has no available AVI codec")
    try:
        for index in range(8):
            writer.write(np.full((48, 64, 3), index * 25, dtype=np.uint8))
    finally:
        writer.release()

    source = EvilEyeBase.create_instance("VideoCaptureOpencv")
    assert isinstance(source, SourceModuleAdapter)
    subscriber = object()
    source.subscribe(subscriber)
    source.set_params(
        type="VideoCaptureOpencv",
        execution_mode="thread",
        source="VideoFile",
        camera=str(video_path),
        apiPreference="CAP_FFMPEG",
        source_ids=[42],
        source_names=["spi-test"],
        loop_play=True,
    )

    try:
        assert source.init() is True
        assert source.execution_mode == "thread"
        assert source.get_runtime_stats()["backend_execution_mode"] == "thread"
        assert source._module.subscribers == [subscriber]
        source.start()

        deadline = time.monotonic() + 45.0
        frames = []
        while not frames and time.monotonic() < deadline:
            frames.extend(source.get())
            if not frames:
                time.sleep(0.02)

        assert frames, (
            "the built-in source adapter did not produce any frames: "
            f"adapter={source.get_runtime_stats()}, "
            f"backend_finished={getattr(source._module, 'finished', None)}, "
            f"backend_working={getattr(source._module, 'is_working', None)}"
        )
        assert all(isinstance(frame, CaptureImage) for frame in frames)
        assert {frame.source_id for frame in frames} == {42}
        assert source.source_names == ["spi-test"]
        assert source.source_address == str(video_path)
        persisted_config = source.get_params()
        assert persisted_config["type"] == "VideoCaptureOpencv"
        assert persisted_config["camera"] == str(video_path)
    finally:
        source.stop()
        source.release()
