"""F01: session principal revalidation and transport revoke."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core.credentials_users import update_credentials_user
from evileye.api.core.transport_revoke import (
    register_metadata_ws,
    register_mjpeg_client,
    revoke_user_transports,
    unregister_metadata_ws,
)
from evileye.api.security import hash_password, resolve_session_principal


ADMIN_PASSWORD = "correct-horse-battery"
OPS_PASSWORD = "ops-secret-password-99"


def _write_creds(tmp_path: Path, *, users=None):
    if users is None:
        users = [
            {
                "username": "admin",
                "password_hash": hash_password(ADMIN_PASSWORD),
                "role": "admin",
                "disabled": False,
            },
            {
                "username": "ops",
                "password_hash": hash_password(OPS_PASSWORD),
                "role": "user",
                "disabled": False,
                "allowed_cameras": ["Cam2"],
            },
            {
                "username": "secondadmin",
                "password_hash": hash_password(OPS_PASSWORD),
                "role": "admin",
                "disabled": False,
            },
        ]
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


def test_resolve_session_principal_rejects_disabled(tmp_path, monkeypatch):
    _write_creds(tmp_path)
    monkeypatch.chdir(tmp_path)
    update_credentials_user("ops", disabled=True)
    assert resolve_session_principal({"username": "ops", "role": "user"}) is None
    assert resolve_session_principal({"username": "admin", "role": "admin"}) is not None


def test_disabled_user_login_rejected(tmp_path, monkeypatch):
    _write_creds(tmp_path)
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert (
        client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code
        == 200
    )
    assert client.patch("/api/v1/users/ops", json={"disabled": True}).status_code == 200
    assert (
        client.post("/api/v1/auth/login", json={"username": "ops", "password": OPS_PASSWORD}).status_code
        == 401
    )


def test_stale_cookie_cleared_after_disable(tmp_path, monkeypatch):
    _write_creds(tmp_path)
    data = tmp_path / "EvilEyeData"
    video = data / "Streams" / "2026-01-01" / "Cam2" / "seg.mp4"
    video.parent.mkdir(parents=True)
    video.write_bytes(b"\x00" * 64)
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(data))
    monkeypatch.chdir(tmp_path)

    ops = TestClient(create_app())
    assert (
        ops.post("/api/v1/auth/login", json={"username": "ops", "password": OPS_PASSWORD}).status_code
        == 200
    )
    assert (
        ops.get("/api/v1/playback/media", params={"path": "Streams/2026-01-01/Cam2/seg.mp4"}).status_code
        == 200
    )

    admin = TestClient(create_app())
    assert (
        admin.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code
        == 200
    )
    assert admin.patch("/api/v1/users/ops", json={"disabled": True}).status_code == 200

    # Same ops client still holds the signed cookie; principal revalidation must 401.
    denied = ops.get("/api/v1/playback/media", params={"path": "Streams/2026-01-01/Cam2/seg.mp4"})
    assert denied.status_code == 401, denied.text


def test_demoted_admin_loses_users_permission(tmp_path, monkeypatch):
    _write_creds(tmp_path)
    monkeypatch.chdir(tmp_path)
    client = TestClient(create_app())
    assert (
        client.post(
            "/api/v1/auth/login", json={"username": "secondadmin", "password": OPS_PASSWORD}
        ).status_code
        == 200
    )
    admin = TestClient(create_app())
    assert (
        admin.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code
        == 200
    )
    demote = admin.patch(
        "/api/v1/users/secondadmin",
        json={"role": "user", "allowed_cameras": ["Cam2"]},
    )
    assert demote.status_code == 200, demote.text
    users = client.get("/api/v1/users")
    assert users.status_code in {401, 403}, users.text


def test_revoke_user_transports_closes_metadata_and_mjpeg():
    ws = MagicMock()
    register_metadata_ws(ws, "ops")
    _cid, cancel = register_mjpeg_client("ops")
    assert not cancel.is_set()
    stats = revoke_user_transports("ops")
    assert stats["metadata"] >= 1
    assert stats["mjpeg"] >= 1
    assert cancel.is_set()
    unregister_metadata_ws(ws)
