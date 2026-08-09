from evileye.api.core.journal_grouping import group_events_rows


def test_group_events_rows_camera_uses_stream_name_not_credentials():
    rows = group_events_rows(
        [
            {
                "event_type": "cam",
                "ts": "2026-08-09T22:00:00",
                "source_names": "Cam2",
                "camera_full_address": "rtsp://user:SecretPass@10.245.1.199",
                "connection_status": True,
            }
        ]
    )
    assert len(rows) == 1
    assert rows[0]["source"] == "Cam2"
    assert rows[0]["information"] == "Camera=Cam2 reconnect"
    assert "SecretPass" not in rows[0]["information"]
    assert "rtsp://" not in rows[0]["information"]


def test_group_events_rows_camera_strips_credentials_from_legacy_url_only_events():
    rows = group_events_rows(
        [
            {
                "event_type": "cam",
                "ts": "2026-08-09T22:00:00",
                "camera_full_address": "rtsp://user:SecretPass@10.245.1.199",
                "connection_status": False,
            }
        ]
    )
    assert rows[0]["source"] == "rtsp://10.245.1.199"
    assert "SecretPass" not in rows[0]["source"]
    assert "SecretPass" not in rows[0]["information"]
