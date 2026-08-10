from evileye.utils.camera_event_label import (
    camera_event_identity,
    format_camera_event_information,
    media_url_without_credentials,
    redact_media_url_credentials,
    sanitize_camera_event_record,
)


def test_media_url_without_credentials_strips_userinfo():
    assert (
        media_url_without_credentials("rtsp://user:AutoZloboglaz821-@10.245.1.199/stream")
        == "rtsp://10.245.1.199/stream"
    )


def test_redact_embedded_credentials_in_free_text():
    text = "Camera=rtsp://user:Secret@10.245.1.202 reconnect"
    assert "Secret" not in redact_media_url_credentials(text)
    assert "rtsp://10.245.1.202" in redact_media_url_credentials(text)


def test_camera_event_identity_prefers_stream_names():
    assert (
        camera_event_identity(
            source_names=["Cam2", "Cam3"],
            address="rtsp://user:pass@10.0.0.1",
        )
        == "Cam2, Cam3"
    )


def test_camera_event_identity_falls_back_to_url_without_creds():
    assert (
        camera_event_identity(source_names=None, address="rtsp://user:pass@10.0.0.1:554/live")
        == "rtsp://10.0.0.1:554/live"
    )


def test_format_camera_event_information_uses_names():
    assert format_camera_event_information("Cam1", connected=True) == "Reconnect [Cam1]"
    assert format_camera_event_information("Cam1", connected=False) == "Disconnect [Cam1]"
    assert format_camera_event_information("Cam2, Cam3", connected=True) == "Reconnect [Cam2, Cam3]"


def test_sanitize_camera_event_record_drops_credentials_and_resolves_name():
    mappings = {"Cam5": (5, "rtsp://user:pass@10.245.1.199")}
    clean = sanitize_camera_event_record(
        {
            "camera_full_address": "rtsp://user:pass@10.245.1.199",
            "connection_status": True,
            "information": "Camera=rtsp://user:pass@10.245.1.199 reconnect",
        },
        source_mappings=mappings,
    )
    assert clean["source_name"] == "Cam5"
    assert clean["camera_full_address"] == "Cam5"
    assert clean["information"] == "Reconnect [Cam5]"
    assert "pass" not in clean["information"]
    assert "rtsp://" not in clean["information"]


def test_sanitize_resolves_split_cameras_to_all_names():
    url = "rtsp://user:pass@10.245.1.199"
    mappings = {
        "Cam2": (2, url),
        "Cam3": (3, url),
    }
    clean = sanitize_camera_event_record(
        {
            "camera_full_address": url,
            "connection_status": True,
        },
        source_mappings=mappings,
    )
    assert clean["source_name"] == "Cam2, Cam3"
    assert clean["information"] == "Reconnect [Cam2, Cam3]"


def test_sanitize_does_not_treat_url_as_stream_name():
    clean = sanitize_camera_event_record(
        {
            "source_name": "rtsp://user:pass@10.0.0.5",
            "camera_full_address": "rtsp://user:pass@10.0.0.5",
            "connection_status": False,
        }
    )
    assert clean["source_name"] == "rtsp://10.0.0.5"
    assert "pass" not in clean["source_name"]
