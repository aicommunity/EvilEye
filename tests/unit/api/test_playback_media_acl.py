"""A03: playback media path allowlist and composite ACL (all parts)."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core.camera_access import CameraAccess
from evileye.api.core.media_access import assert_media_path_allowed, cameras_from_media_path
from evileye.api.security import hash_password
from fastapi import HTTPException


ADMIN_PASSWORD = "correct-horse-battery"
USER_PASSWORD = "secretpassword"


def test_cameras_from_media_path_streams_and_composite():
    assert cameras_from_media_path("Streams/2026-01-01/Cam2/file.mp4") == ["Cam2"]
    assert cameras_from_media_path("Streams/2026-01-01/Cam2-Cam3/x.mp4") == ["Cam2", "Cam3"]
    assert cameras_from_media_path("Detections/2026-01-01/x.json") is None
    assert cameras_from_media_path("configs/system.json") is None
    assert cameras_from_media_path("Events/2026-01-01/Videos/Cam2/clip.mp4") == ["Cam2"]
    assert cameras_from_media_path("Events/2026-01-01/Cam9/clip.mp4") == ["Cam9"]
    assert cameras_from_media_path("Events/2026-01-01/Videos/x.mp4") is None
    assert cameras_from_media_path("Events/2026-01-01/Metadata/x.json") is None


def test_assert_media_composite_requires_all():
    access = CameraAccess(
        unrestricted=False,
        allowed_names=frozenset({"Cam2"}),
        visible_names=None,
    )
    with pytest.raises(HTTPException) as exc:
        assert_media_path_allowed(access, "Streams/2026-01-01/Cam2-Cam3/x.mp4")
    assert exc.value.status_code == 403

    access2 = CameraAccess(
        unrestricted=False,
        allowed_names=frozenset({"Cam2", "Cam3"}),
        visible_names=None,
    )
    assert_media_path_allowed(access2, "Streams/2026-01-01/Cam2-Cam3/x.mp4")


def test_assert_media_denies_unmapped_for_restricted():
    access = CameraAccess(
        unrestricted=False,
        allowed_names=frozenset({"Cam2"}),
        visible_names=None,
    )
    with pytest.raises(HTTPException) as exc:
        assert_media_path_allowed(access, "Detections/foo.bin")
    assert exc.value.status_code == 403


def _write_creds(tmp_path, *, extra_users=None):
    users = [
        {
            "username": "admin",
            "password_hash": hash_password(ADMIN_PASSWORD),
            "role": "admin",
            "disabled": False,
        }
    ]
    if extra_users:
        users.extend(extra_users)
    creds = {
        "web_auth": {
            "enabled": True,
            "session_secret": "test-session-secret-not-default-0123456789",
            "internal_token": "test-internal-token",
            "secure_cookies": False,
            "users": users,
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    (tmp_path / "web_users.json").write_text(json.dumps({"users": []}), encoding="utf-8")


def test_playback_media_acl_http(tmp_path, monkeypatch):
    data = tmp_path / "EvilEyeData"
    cam_file = data / "Streams" / "2026-01-01" / "Cam2" / "seg.mp4"
    cam_file.parent.mkdir(parents=True)
    cam_file.write_bytes(b"fake-mp4")
    composite = data / "Streams" / "2026-01-01" / "Cam2-Cam3" / "seg.mp4"
    composite.parent.mkdir(parents=True)
    composite.write_bytes(b"fake-composite")
    outside = data / "Detections" / "2026-01-01" / "x.bin"
    outside.parent.mkdir(parents=True)
    outside.write_bytes(b"secret")
    events_ok = data / "Events" / "2026-01-01" / "Videos" / "Cam2" / "clip.mp4"
    events_ok.parent.mkdir(parents=True)
    events_ok.write_bytes(b"event-mp4")
    events_denied = data / "Events" / "2026-01-01" / "Videos" / "Cam9" / "clip.mp4"
    events_denied.parent.mkdir(parents=True)
    events_denied.write_bytes(b"other-event")

    _write_creds(
        tmp_path,
        extra_users=[
            {
                "username": "ops",
                "password_hash": hash_password(USER_PASSWORD),
                "role": "user",
                "disabled": False,
                "allowed_cameras": ["Cam2"],
            }
        ],
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(data))
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops", "password": USER_PASSWORD},
    ).status_code == 200

    ok = client.get(
        "/api/v1/playback/media",
        params={"path": "Streams/2026-01-01/Cam2/seg.mp4"},
    )
    assert ok.status_code == 200
    assert ok.content == b"fake-mp4"

    denied = client.get(
        "/api/v1/playback/media",
        params={"path": "Streams/2026-01-01/Cam2-Cam3/seg.mp4"},
    )
    assert denied.status_code == 403

    outside_res = client.get(
        "/api/v1/playback/media",
        params={"path": "Detections/2026-01-01/x.bin"},
    )
    assert outside_res.status_code in {403, 404}

    ev_ok = client.get(
        "/api/v1/playback/media",
        params={"path": "Events/2026-01-01/Videos/Cam2/clip.mp4"},
    )
    assert ev_ok.status_code == 200
    assert ev_ok.content == b"event-mp4"

    ev_denied = client.get(
        "/api/v1/playback/media",
        params={"path": "Events/2026-01-01/Videos/Cam9/clip.mp4"},
    )
    assert ev_denied.status_code == 403
