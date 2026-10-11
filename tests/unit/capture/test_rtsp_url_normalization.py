import pytest

from evileye.capture.video_capture_opencv import VideoCaptureOpencv


@pytest.mark.parametrize(
    ("camera", "credentials", "expected_url", "expected_pure_url"),
    [
        (
            "rtsp://url-user:url-pass@127.0.0.1:18554/live",
            {},
            "rtsp://url-user:url-pass@127.0.0.1:18554/live",
            "rtsp://127.0.0.1:18554/live",
        ),
        (
            "rtsp://127.0.0.1:18554/live",
            {"username": "config-user", "password": "config-pass"},
            "rtsp://config-user:config-pass@127.0.0.1:18554/live",
            "rtsp://127.0.0.1:18554/live",
        ),
        (
            "rtsp://url-user:url-pass@[::1]:18554/live",
            {},
            "rtsp://url-user:url-pass@[::1]:18554/live",
            "rtsp://[::1]:18554/live",
        ),
    ],
)
def test_ip_camera_url_normalization_preserves_port_and_ipv6(
    camera, credentials, expected_url, expected_pure_url
):
    source = VideoCaptureOpencv()
    source.set_params(
        source="IpCamera",
        camera=camera,
        source_ids=[1],
        source_names=["test-camera"],
        **credentials,
    )

    assert source.source_address == expected_url
    assert source.pure_url == expected_pure_url
