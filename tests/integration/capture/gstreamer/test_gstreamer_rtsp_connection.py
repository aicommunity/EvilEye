"""RTSP transport and recording checks.

Live tests use credentials from the environment and never print pipeline strings,
URLs containing credentials, usernames, or passwords.
"""

import os
import shutil
import sys
import subprocess
import time
from pathlib import Path

import pytest


def _rtsp_credentials(*, require_password=True):
    camera_url = os.environ.get("EVILEYE_TEST_RTSP_URL", "rtsp://10.245.1.199")
    username = os.environ.get("EVILEYE_TEST_RTSP_USER", "user")
    password = os.environ.get("EVILEYE_TEST_RTSP_PASSWORD", "")
    if require_password and not password:
        pytest.skip("Set EVILEYE_TEST_RTSP_PASSWORD to run live RTSP tests")
    return camera_url, username, password or "test_password"


def _synthetic_credentials():
    return "rtsp://127.0.0.1:8554/stream", "test-user", "test-password"


def _new_capture(camera_url, username, password, *, protocol, record=None):
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

    capture = VideoCaptureGStreamer()
    params = {
        "execution_mode": "thread",
        "source": "IpCamera",
        "camera": camera_url,
        "source_ids": [0],
        "source_names": ["TestCam"],
        "username": username,
        "password": password,
    }
    if record is not None:
        params["record"] = record
    capture.set_params(**params)
    capture._rtsp_protocol = protocol
    return capture


def _wait_for_frame(capture, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for frame in capture.get() or []:
            image = getattr(frame, "image", None)
            if image is not None:
                return frame
        time.sleep(0.1)
    return None


def _recording_config(out_dir):
    return {
        "enabled": True,
        "continuous_recording_enabled": True,
        "container": "mp4",
        "segment_length_sec": 300,
        "retention_days": 1,
        "min_free_space_pct": 0,
        "min_file_size_kb": 0,
        "out_dir": str(out_dir),
        "filename_tmpl": "{source_name}_{start_time}_{seq}.{ext}",
    }


def test_rtsp_pipeline_generation_masks_credentials():
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer
    from evileye.capture.video_capture_base import CaptureDeviceType

    camera_url, username, password = _synthetic_credentials()
    capture = VideoCaptureGStreamer()
    capture.source_type = CaptureDeviceType.IpCamera
    capture.source_address = camera_url
    capture.username = username
    capture.password = password
    capture._rtsp_protocol = "tcp"

    pipeline = capture._build_pipeline()
    sanitized = capture._mask_credentials_in_pipeline(pipeline)

    assert "rtspsrc" in pipeline
    assert "protocols=tcp" in pipeline
    assert "user-id=" in pipeline
    assert "user-pw=" in pipeline
    assert "rtph265depay" in pipeline or "rtph264depay" in pipeline
    assert "videoconvert" in pipeline
    assert username not in sanitized
    assert password not in sanitized


def test_rtsp_recording_pipeline_has_bounded_recording_queue():
    camera_url, username, password = _synthetic_credentials()
    capture = _new_capture(
        camera_url,
        username,
        password,
        protocol="tcp",
        record=_recording_config(Path("/tmp/evileye-rtsp-recording-test")),
    )

    pipeline = capture._build_pipeline()

    assert "tee name=t" in pipeline
    assert "recording_queue" in pipeline
    assert "appsink name=sink" in pipeline


def _run_live_camera(protocol, record_dir=None):
    camera_url, username, password = _rtsp_credentials()
    record = _recording_config(Path(record_dir)) if record_dir else None
    capture = _new_capture(
        camera_url, username, password, protocol=protocol, record=record
    )

    try:
        initialized = capture.init()
        assert initialized, (
            "GStreamer RTSP initialization failed "
            f"({type(capture._last_init_error).__name__})"
        )
        frame = _wait_for_frame(capture)
        assert frame is not None, "RTSP source produced no frame"
        assert frame.image.ndim == 3
        assert frame.image.shape[2] == 3
        if record_dir:
            time.sleep(3.0)
    finally:
        capture.stop()
        capture.release()


def _run_isolated_live_check(protocol, record_dir=None):
    worker_code = (
        "import runpy, sys; "
        "ns=runpy.run_path(sys.argv[1]); "
        "ns['_run_live_camera'](sys.argv[2], sys.argv[3] or None)"
    )
    try:
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                worker_code,
                str(Path(__file__).resolve()),
                protocol,
                str(record_dir or ""),
            ],
            capture_output=True,
            text=True,
            timeout=60,
            env=os.environ.copy(),
        )
    except subprocess.TimeoutExpired:
        pytest.fail("Isolated RTSP worker exceeded 60 seconds; captured output suppressed")
    if result.returncode == 0:
        return

    username = os.environ.get("EVILEYE_TEST_RTSP_USER", "")
    password = os.environ.get("EVILEYE_TEST_RTSP_PASSWORD", "")
    stderr = result.stderr
    stdout = result.stdout
    for secret in (username, password):
        if secret:
            stderr = stderr.replace(secret, "****")
            stdout = stdout.replace(secret, "****")
    pytest.fail(
        f"Isolated RTSP worker exited with code {result.returncode}. "
        f"stdout={stdout[-1000:]!r}; stderr={stderr[-2000:]!r}"
    )


def test_rtsp_camera_over_tcp_returns_bgr_frame(tmp_path):
    _rtsp_credentials()
    _run_isolated_live_check("tcp")


def test_rtsp_camera_writes_mp4_with_shared_recorder(tmp_path):
    ffprobe = shutil.which("ffprobe")
    if ffprobe is None:
        pytest.skip("ffprobe is required to inspect the recorded segment")

    _rtsp_credentials()
    output_dir = tmp_path / "Recording"
    _run_isolated_live_check("udp+tcp", output_dir)

    segments = list((output_dir / "Streams").rglob("*.mp4"))
    assert segments, f"RTSP recording produced no MP4 under {output_dir}"
    probe = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-select_streams", "v:0",
            "-count_packets",
            "-show_entries", "stream=nb_read_packets",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(segments[0]),
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert int(probe.stdout.strip()) > 0
