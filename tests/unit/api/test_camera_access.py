"""Camera ACL, user prefs, and /auth/me extensions."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.security import hash_password


ADMIN_PASSWORD = "correct-horse-battery"
USER_PASSWORD = "secretpassword"


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


def _client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_creds(tmp_path)
    app = create_app()
    return TestClient(app), app


def test_patch_allowed_cameras_store_and_credentials(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    patched = client.patch(
        "/api/v1/users/ops@example.com",
        json={"allowed_cameras": ["Cam1", "Cam2"]},
    )
    assert patched.status_code == 200
    assert patched.json()["user"]["allowed_cameras"] == ["Cam1", "Cam2"]

    items = client.get("/api/v1/users").json()["items"]
    ops = next(u for u in items if u["id"] == "ops@example.com")
    assert ops["allowed_cameras"] == ["Cam1", "Cam2"]

    # credentials user can also receive ACL
    cred_patch = client.patch("/api/v1/users/admin", json={"allowed_cameras": ["Cam9"]})
    assert cred_patch.status_code == 200
    assert cred_patch.json()["user"]["allowed_cameras"] == ["Cam9"]


def test_empty_acl_hides_cameras_for_user(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    client.post("/api/v1/auth/logout")

    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": USER_PASSWORD},
    ).status_code == 200
    me = client.get("/api/v1/auth/me").json()
    assert me["camera_access"] == "restricted"
    assert me["allowed_cameras"] == []

    cams = client.get("/api/v1/state/cameras?scope=active").json()
    assert cams["items"] == []


def test_acl_filters_state_cameras(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    client.patch("/api/v1/users/ops@example.com", json={"allowed_cameras": ["Cam1"]})

    def fake_summaries(scope="active"):
        return [
            {"run_id": 1, "source_id": 0, "source_name": "Cam1", "preview_available": False, "alive": True},
            {"run_id": 1, "source_id": 1, "source_name": "Cam2", "preview_available": False, "alive": True},
        ]

    monkeypatch.setattr("evileye.api.routes.state.list_camera_summaries", fake_summaries)
    monkeypatch.setattr("evileye.api.routes.state.get_cached_camera_summaries", lambda scope: None)

    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": USER_PASSWORD},
    ).status_code == 200
    items = client.get("/api/v1/state/cameras?scope=active").json()["items"]
    assert [c["source_name"] for c in items] == ["Cam1"]


def test_admin_sees_all_cameras_despite_acl_field(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.patch("/api/v1/users/admin", json={"allowed_cameras": []})

    def fake_summaries(scope="active"):
        return [
            {"run_id": 1, "source_id": 0, "source_name": "Cam1", "preview_available": False, "alive": True},
            {"run_id": 1, "source_id": 1, "source_name": "Cam2", "preview_available": False, "alive": True},
        ]

    monkeypatch.setattr("evileye.api.routes.state.list_camera_summaries", fake_summaries)
    monkeypatch.setattr("evileye.api.routes.state.get_cached_camera_summaries", lambda scope: None)

    items = client.get("/api/v1/state/cameras?scope=active").json()["items"]
    assert [c["source_name"] for c in items] == ["Cam1", "Cam2"]
    me = client.get("/api/v1/auth/me").json()
    assert me["camera_access"] == "all"


def test_prefs_visible_cameras_narrows_list(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    client.patch("/api/v1/users/ops@example.com", json={"allowed_cameras": ["Cam1", "Cam2"]})
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": USER_PASSWORD},
    ).status_code == 200

    put = client.put("/api/v1/auth/prefs", json={"visible_cameras": ["Cam1"], "lang": "en"})
    assert put.status_code == 200
    assert put.json()["prefs"]["visible_cameras"] == ["Cam1"]
    assert put.json()["prefs"]["lang"] == "en"

    def fake_summaries(scope="active"):
        return [
            {"run_id": 1, "source_id": 0, "source_name": "Cam1", "preview_available": False, "alive": True},
            {"run_id": 1, "source_id": 1, "source_name": "Cam2", "preview_available": False, "alive": True},
        ]

    monkeypatch.setattr("evileye.api.routes.state.list_camera_summaries", fake_summaries)
    monkeypatch.setattr("evileye.api.routes.state.get_cached_camera_summaries", lambda scope: None)

    items = client.get("/api/v1/state/cameras?scope=active").json()["items"]
    assert [c["source_name"] for c in items] == ["Cam1"]


def test_playback_cameras_respect_acl(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    client.patch("/api/v1/users/ops@example.com", json={"allowed_cameras": ["Cam1"]})
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": USER_PASSWORD},
    ).status_code == 200

    monkeypatch.setattr(
        "evileye.api.core.playback_service.discover_cameras",
        lambda date=None: [
            {"id": "Cam1", "name": "Cam1"},
            {"id": "Cam2", "name": "Cam2"},
        ],
    )
    items = client.get("/api/v1/playback/cameras").json()["items"]
    assert [c["id"] for c in items] == ["Cam1"]

    denied = client.get("/api/v1/playback/segments", params={"camera": "Cam2"})
    assert denied.status_code == 403


def test_camera_catalog_requires_users_manage(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": USER_PASSWORD, "role": "user"},
    )
    assert client.get("/api/v1/users/camera-catalog").status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": USER_PASSWORD},
    ).status_code == 200
    assert client.get("/api/v1/users/camera-catalog").status_code == 403
