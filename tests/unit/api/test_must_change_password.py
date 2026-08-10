from pathlib import Path

from evileye.api.core.credentials_users import set_credentials_password
from evileye.api.core.web_auth_bootstrap import (
    ensure_default_admin_credentials,
    user_must_change_password,
)


def test_bootstrap_sets_must_change_password(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    creds = tmp_path / "credentials.json"
    creds.write_text('{"web_auth": {"enabled": true, "users": []}}\n', encoding="utf-8")
    monkeypatch.setenv("EVILEYE_BOOTSTRAP_ADMIN_PASSWORD", "bootstrap-secret")
    assert ensure_default_admin_credentials(creds) is True
    users = __import__("json").loads(creds.read_text(encoding="utf-8"))["web_auth"]["users"]
    assert users[0]["must_change_password"] is True
    assert user_must_change_password(users[0]) is True


def test_existing_user_without_flag_not_forced(tmp_path: Path):
    record = {"username": "admin", "password_hash": "x", "role": "admin"}
    assert user_must_change_password(record) is False


def test_explicit_false_flag_respected():
    assert user_must_change_password({"must_change_password": False}) is False


def test_insecure_plaintext_forces_change():
    assert user_must_change_password({"password": "change-me"}) is True


def test_change_password_clears_flag(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    creds = tmp_path / "credentials.json"
    from evileye.api.security import hash_password
    import json

    payload = {
        "web_auth": {
            "enabled": True,
            "users": [
                {
                    "username": "admin",
                    "password_hash": hash_password("old-password"),
                    "role": "admin",
                    "must_change_password": True,
                }
            ],
        }
    }
    creds.write_text(json.dumps(payload), encoding="utf-8")
    set_credentials_password("admin", "new-password-ok", path=creds)
    users = json.loads(creds.read_text(encoding="utf-8"))["web_auth"]["users"]
    assert users[0]["must_change_password"] is False
