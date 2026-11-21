import json

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app


@pytest.fixture
def events_client(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-19"
    meta = root / "Events" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "zone_events_entered.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-08-19T12:00:00",
                    "source_name": "Cam2",
                    "event_name": "ZoneA",
                    "zone_name": "ZoneA",
                    "zone_id": "zone-a",
                }
            ]
        ),
        encoding="utf-8",
    )
    (meta / "zone_events_left.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-08-19T12:00:04",
                    "source_name": "Cam2",
                    "event_name": "ZoneA",
                    "zone_name": "ZoneA",
                    "zone_id": "zone-a",
                }
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "credentials.json").write_text(
        json.dumps(
            {
                "web_auth": {
                    "enabled": False,
                    "users": [{"username": "test", "password": "test", "role": "admin"}],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_playback_events_returns_intervals_and_legacy(events_client):
    res = events_client.get(
        "/api/v1/playback/events",
        params={"camera": "Cam2", "date": "2026-08-19"},
    )
    assert res.status_code == 200
    payload = res.json()
    assert "items" in payload
    assert "legacy_markers" in payload
    assert isinstance(payload["items"], list)
    assert isinstance(payload["legacy_markers"], list)
    assert len(payload["items"]) == 1
    interval = payload["items"][0]
    assert interval["camera"] == "Cam2"
    assert interval["zone_name"] == "ZoneA"
    assert interval["start_ts"] <= interval["end_ts"]
