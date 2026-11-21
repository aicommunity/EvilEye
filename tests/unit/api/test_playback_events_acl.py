"""A04: playback events injects camera ACL when filter omitted."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.security import hash_password

ADMIN_PASSWORD = "correct-horse-battery"
USER_PASSWORD = "secretpassword"


def _seed_events(root, date: str = "2026-08-19"):
    meta = root / "Events" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "zone_events_entered.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": f"{date}T12:00:00",
                    "source_name": "Cam1",
                    "event_name": "Z1",
                    "zone_name": "Z1",
                    "zone_id": "z1",
                },
                {
                    "timestamp": f"{date}T12:01:00",
                    "source_name": "Cam2",
                    "event_name": "Z2",
                    "zone_name": "Z2",
                    "zone_id": "z2",
                },
                {
                    "timestamp": f"{date}T12:02:00",
                    "source_name": "System",
                    "event_name": "sys",
                    "zone_name": "sys",
                    "zone_id": "sys",
                },
            ]
        ),
        encoding="utf-8",
    )
    (meta / "zone_events_left.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": f"{date}T12:00:04",
                    "source_name": "Cam1",
                    "event_name": "Z1",
                    "zone_name": "Z1",
                    "zone_id": "z1",
                },
                {
                    "timestamp": f"{date}T12:01:04",
                    "source_name": "Cam2",
                    "event_name": "Z2",
                    "zone_name": "Z2",
                    "zone_id": "z2",
                },
                {
                    "timestamp": f"{date}T12:02:04",
                    "source_name": "System",
                    "event_name": "sys",
                    "zone_name": "sys",
                    "zone_id": "sys",
                },
            ]
        ),
        encoding="utf-8",
    )


def test_playback_events_without_camera_respects_acl(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    _seed_events(root)
    creds = {
        "web_auth": {
            "enabled": True,
            "session_secret": "test-session-secret-not-default-0123456789",
            "internal_token": "tok",
            "secure_cookies": False,
            "users": [
                {
                    "username": "admin",
                    "password_hash": hash_password(ADMIN_PASSWORD),
                    "role": "admin",
                    "disabled": False,
                },
                {
                    "username": "ops",
                    "password_hash": hash_password(USER_PASSWORD),
                    "role": "user",
                    "disabled": False,
                    "allowed_cameras": ["Cam2"],
                },
            ],
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    (tmp_path / "web_users.json").write_text(json.dumps({"users": []}), encoding="utf-8")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())

    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops", "password": USER_PASSWORD},
    ).status_code == 200
    res = client.get("/api/v1/playback/events", params={"date": "2026-08-19"})
    assert res.status_code == 200
    cams = {it.get("camera") for it in res.json().get("items") or []}
    assert cams == {"Cam2", "System"}
    assert "Cam1" not in cams

    denied = client.get(
        "/api/v1/playback/events",
        params={"camera": "Cam1", "date": "2026-08-19"},
    )
    assert denied.status_code == 403

    empty_acl_creds = json.loads((tmp_path / "credentials.json").read_text(encoding="utf-8"))
    empty_acl_creds["web_auth"]["users"].append(
        {
            "username": "nobody",
            "password_hash": hash_password(USER_PASSWORD),
            "role": "user",
            "disabled": False,
            "allowed_cameras": [],
        }
    )
    (tmp_path / "credentials.json").write_text(json.dumps(empty_acl_creds), encoding="utf-8")
    client2 = TestClient(create_app())
    assert client2.post(
        "/api/v1/auth/login",
        json={"username": "nobody", "password": USER_PASSWORD},
    ).status_code == 200
    empty_res = client2.get("/api/v1/playback/events", params={"date": "2026-08-19"})
    assert empty_res.status_code == 403
