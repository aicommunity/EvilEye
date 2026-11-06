from __future__ import annotations

import time

import pytest


def _ensure_gst_available():
    try:
        import gi

        gi.require_version("Gst", "1.0")
        from gi.repository import Gst

        Gst.init(None)
    except Exception as exc:
        pytest.skip(f"GStreamer is unavailable: {exc}")


@pytest.mark.parametrize("backend", ["opencv", "gstreamer"])
@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_builtin_rtsp_source_delivers_frames(
    backend, execution_mode, local_rtsp_fixture, monkeypatch
):
    if backend == "opencv":
        from evileye.capture.video_capture_opencv import VideoCaptureOpencv

        source = VideoCaptureOpencv()
        monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        extra_params = {"apiPreference": "CAP_FFMPEG"}
    else:
        _ensure_gst_available()
        from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

        source = VideoCaptureGStreamer()
        extra_params = {}

    source.set_params(
        source="IpCamera",
        camera=local_rtsp_fixture.url,
        source_ids=[0],
        source_names=[f"local-rtsp-{backend}"],
        execution_mode=execution_mode,
        desired_fps=15,
        capture={"frame_timeout_seconds": 5, "init_grace_period_seconds": 2},
        reconnect={
            "initial_delay_sec": 0.2,
            "backoff_step_sec": 0.2,
            "max_delay_sec": 1,
            "min_interval_sec": 0,
        },
        **extra_params,
    )
    try:
        assert source.init() is True
        source.start()
        frames = []
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline and not frames:
            frames = source.get() or []
            if not frames:
                time.sleep(0.05)

        assert frames, (
            f"{backend}/{execution_mode} returned no RTSP frames; "
            f"health={source.get_capture_health()}, "
            f"last_error={getattr(source, '_last_init_error', None)!r}, "
            f"pipeline={source.pipeline is not None}, "
            f"callbacks={getattr(source, '_callback_count', None)}, "
            f"reconnecting={getattr(source, '_reconnecting', None)}"
            f", server_log={local_rtsp_fixture.log_tail()}"
        )
        frame = frames[0]
        assert frame.source_id == 0
        assert frame.image is not None
        assert frame.image.ndim == 3
        assert frame.image.shape[2] == 3
    finally:
        source.stop()
        source.release()


@pytest.mark.parametrize("backend", ["opencv", "gstreamer"])
@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_builtin_rtsp_source_recovers_after_publisher_restart(
    backend, execution_mode, local_rtsp_fixture, monkeypatch
):
    if backend == "opencv":
        from evileye.capture.video_capture_opencv import VideoCaptureOpencv

        source = VideoCaptureOpencv()
        monkeypatch.setenv("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")
        extra_params = {"apiPreference": "CAP_FFMPEG"}
    else:
        _ensure_gst_available()
        from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

        source = VideoCaptureGStreamer()
        extra_params = {}

    source.set_params(
        source="IpCamera",
        camera=local_rtsp_fixture.url,
        source_ids=[0],
        source_names=[f"restart-rtsp-{backend}"],
        execution_mode=execution_mode,
        desired_fps=15,
        capture={"frame_timeout_seconds": 5, "init_grace_period_seconds": 2},
        reconnect={
            "initial_delay_sec": 0.2,
            "backoff_step_sec": 0.2,
            "max_delay_sec": 1,
            "min_interval_sec": 0,
            "monitor_interval_sec": 0.2,
        },
        **extra_params,
    )
    publisher_stopped = False
    try:
        assert source.init() is True
        source.start()
        deadline = time.monotonic() + 15
        first_frames = []
        while time.monotonic() < deadline and not first_frames:
            first_frames = source.get() or []
            if not first_frames:
                time.sleep(0.05)
        assert first_frames, f"{backend}/{execution_mode} did not receive the initial RTSP frame"

        initial_health = source.get_capture_health()
        local_rtsp_fixture.stop_publisher()
        publisher_stopped = True
        if execution_mode == "thread":
            outage_deadline = time.monotonic() + 10
            while time.monotonic() < outage_deadline:
                if source.get_capture_health()["disconnect_count"] > initial_health["disconnect_count"]:
                    break
                time.sleep(0.1)
            assert source.get_capture_health()["disconnect_count"] > initial_health["disconnect_count"], (
                f"{backend}/{execution_mode} did not report the RTSP publisher outage; "
                f"health={source.get_capture_health()}, server_log={local_rtsp_fixture.log_tail()}"
            )
        else:
            # The process API exposes connection generation on recovered frames;
            # its health snapshot does not forward child disconnect counters.
            time.sleep(3.0)

        drain_deadline = time.monotonic() + 1.0
        while time.monotonic() < drain_deadline:
            source.get()
            time.sleep(0.05)

        local_rtsp_fixture.start_publisher()
        publisher_stopped = False
        reconnect_deadline = time.monotonic() + 20
        recovered_frames = []
        while time.monotonic() < reconnect_deadline:
            recovered_frames = source.get() or []
            health = source.get_capture_health()
            if recovered_frames and health["backend_connection_generation"] > initial_health[
                "backend_connection_generation"
            ]:
                break
            time.sleep(0.05)

        assert recovered_frames, (
            f"{backend}/{execution_mode} did not recover after publisher restart; "
            f"health={source.get_capture_health()}, server_log={local_rtsp_fixture.log_tail()}"
        )
        assert source.get_capture_health()["backend_connection_generation"] > initial_health[
            "backend_connection_generation"
        ]
    finally:
        source.stop()
        source.release()
        if publisher_stopped:
            local_rtsp_fixture.start_publisher()
