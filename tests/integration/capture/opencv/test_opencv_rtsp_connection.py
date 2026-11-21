"""Opt-in live RTSP checks for the built-in OpenCV source module."""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import pytest


def _live_camera_credentials():
    camera_url = os.environ.get("EVILEYE_TEST_RTSP_URL", "rtsp://10.245.1.199")
    username = os.environ.get("EVILEYE_TEST_RTSP_USER", "user")
    password = os.environ.get("EVILEYE_TEST_RTSP_PASSWORD", "")
    if not password:
        pytest.skip("Set EVILEYE_TEST_RTSP_PASSWORD to run live RTSP tests")
    return camera_url, username, password


def _run_live_camera():
    camera_url, username, password = _live_camera_credentials()

    from evileye.core.base_class import EvilEyeBase
    from evileye.core.frame import CaptureImage
    import evileye.capture.video_capture_opencv  # noqa: F401

    source = EvilEyeBase.create_instance("VideoCaptureOpencv")
    source.set_params(
        type="VideoCaptureOpencv",
        execution_mode="thread",
        source="IpCamera",
        camera=camera_url,
        username=username,
        password=password,
        apiPreference="CAP_FFMPEG",
        source_ids=[0],
        source_names=["opencv-rtsp-integration"],
        loop_play=False,
    )

    try:
        assert source.init(), "OpenCV source initialization failed"
        source.start()
        deadline = time.monotonic() + 12.0
        frame = None
        while time.monotonic() < deadline:
            frames = source.get() or []
            if frames:
                frame = frames[0]
                break
            time.sleep(0.05)

        assert isinstance(frame, CaptureImage), "RTSP source produced no frame"
        assert frame.image is not None
        assert frame.image.ndim == 3
        assert frame.image.shape[2] == 3
        assert frame.source_id == 0
    finally:
        source.stop()
        source.release()


def _run_isolated_live_camera():
    worker_code = (
        "import runpy, sys; "
        "ns=runpy.run_path(sys.argv[1]); ns['_run_live_camera']()"
    )
    try:
        result = subprocess.run(
            [sys.executable, "-c", worker_code, str(Path(__file__).resolve())],
            capture_output=True,
            text=True,
            timeout=30,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Isolated OpenCV RTSP worker exceeded 30 seconds")

    if result.returncode == 0:
        return

    stdout = result.stdout
    stderr = result.stderr
    for secret in (
        os.environ.get("EVILEYE_TEST_RTSP_USER", ""),
        os.environ.get("EVILEYE_TEST_RTSP_PASSWORD", ""),
    ):
        if secret:
            for value in {secret, quote(secret, safe="")}:
                stdout = stdout.replace(value, "****")
                stderr = stderr.replace(value, "****")
    pytest.fail(
        f"Isolated OpenCV RTSP worker exited with code {result.returncode}. "
        f"stdout={stdout[-1000:]!r}; stderr={stderr[-2000:]!r}"
    )


def test_opencv_builtin_source_receives_bgr_frame_from_rtsp():
    _live_camera_credentials()
    _run_isolated_live_camera()
