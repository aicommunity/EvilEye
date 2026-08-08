"""Unified users list, change-password, PATCH/DELETE across dual-store."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.security import hash_password


ADMIN_PASSWORD = "correct-horse-battery"
NEW_PASSWORD = "new-password-99"


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


def test_list_users_includes_credentials_admin(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    items = client.get("/api/v1/users").json()["items"]
    admin = next(u for u in items if u["username"] == "admin")
    assert admin["source"] == "credentials"
    assert admin["role"] == "admin"
    assert admin["status"] == "approved"


def test_create_store_user_appears_in_list(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    created = client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": "secretpassword", "role": "user"},
    )
    assert created.status_code == 200
    assert created.json()["user"]["source"] == "store"
    items = client.get("/api/v1/users").json()["items"]
    assert any(u["id"] == "ops@example.com" and u["source"] == "store" for u in items)


def test_change_password_credentials_admin(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": ADMIN_PASSWORD, "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": NEW_PASSWORD}).status_code == 200


def test_change_password_wrong_current(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    bad = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": "wrong-password", "new_password": NEW_PASSWORD},
    )
    assert bad.status_code == 401


def test_patch_role_and_password_store_user(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "ops@example.com", "password": "secretpassword", "role": "user"},
    )
    patched = client.patch(
        "/api/v1/users/ops@example.com",
        json={"role": "admin", "password": "resetpassword1"},
    )
    assert patched.status_code == 200
    assert patched.json()["user"]["role"] == "admin"
    client.post("/api/v1/auth/logout")
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "ops@example.com", "password": "resetpassword1"},
    ).status_code == 200


def test_patch_password_credentials_admin(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    # Create second admin so we can demote/disable freely later if needed
    client.post(
        "/api/v1/users",
        json={"email": "second@example.com", "password": "secretpassword", "role": "admin"},
    )
    patched = client.patch("/api/v1/users/admin", json={"password": NEW_PASSWORD})
    assert patched.status_code == 200
    client.post("/api/v1/auth/logout")
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": NEW_PASSWORD}).status_code == 200


def test_delete_last_admin_forbidden(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    # Create a non-admin so session still has someone; try delete self/last admin
    res = client.delete("/api/v1/users/admin")
    assert res.status_code == 400


def test_delete_self_forbidden(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    client.post(
        "/api/v1/users",
        json={"email": "second@example.com", "password": "secretpassword", "role": "admin"},
    )
    res = client.delete("/api/v1/users/admin")
    assert res.status_code == 400
    assert "yourself" in res.json()["detail"].lower()


def test_approve_reject_regression(tmp_path, monkeypatch):
    client, app = _client(tmp_path, monkeypatch)
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": ADMIN_PASSWORD}).status_code == 200
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "pending@example.com", "password": "secretpassword"},
    )
    assert reg.status_code == 200
    assert client.post("/api/v1/users/pending@example.com/approve").status_code == 200
    app.state.web_auth = __import__("evileye.api.security", fromlist=["load_web_auth_config"]).load_web_auth_config()
    assert client.post(
        "/api/v1/auth/login",
        json={"username": "pending@example.com", "password": "secretpassword"},
    ).status_code == 200
