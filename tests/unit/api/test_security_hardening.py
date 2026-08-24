"""Security hardening regression tests."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evileye.api.core.ip_ban_store import reset_ip_ban_store_for_tests
from evileye.api.core.public_base_url import resolve_public_api_base_url
from evileye.api.core.rate_guard import ProtectionConfig, reset_rate_guard_for_tests
from evileye.api.core.safe_paths import UnsafePathError, safe_config_name, assert_under_dir
from evileye.api.core.log_service import redact_secrets
from evileye.api.core.web_auth_bootstrap import ensure_default_admin_credentials
from evileye.api.security import hash_password, verify_password


def test_safe_config_name_rejects_traversal():
    with pytest.raises(UnsafePathError):
        safe_config_name("../credentials.json")
    with pytest.raises(UnsafePathError):
        safe_config_name("foo/bar.json")
    assert safe_config_name("ok.json") == "ok.json"


def test_assert_under_dir_rejects_prefix_sibling(tmp_path):
    base = tmp_path / "EvilEyeData"
    base.mkdir()
    sibling = tmp_path / "EvilEyeData_evil"
    sibling.mkdir()
    secret = sibling / "secret.txt"
    secret.write_text("x", encoding="utf-8")
    with pytest.raises(UnsafePathError):
        assert_under_dir(secret, base)


def test_redact_secrets():
    text = "rtsp://user:secret@cam/stream password=hunter2"
    out = redact_secrets(text)
    assert "secret" not in out
    assert "hunter2" not in out
    assert "***:***@" in out


def test_resolve_public_api_base_url_ignores_host(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVILEYE_WEB_API_BASE", "http://127.0.0.1:8181/api/v1")
    monkeypatch.delenv("EVILEYE_HTTP_PORT", raising=False)
    assert resolve_public_api_base_url() == "http://127.0.0.1:8181/api/v1"


def test_bootstrap_no_plaintext_and_has_tokens(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_BOOTSTRAP_ADMIN_PASSWORD", raising=False)
    monkeypatch.delenv("EVILEYE_SESSION_SECRET", raising=False)
    monkeypatch.delenv("EVILEYE_INTERNAL_TOKEN", raising=False)
    path = tmp_path / "credentials.json"
    assert ensure_default_admin_credentials(path) is True
    payload = json.loads(path.read_text(encoding="utf-8"))
    user = payload["web_auth"]["users"][0]
    assert "password" not in user or not user.get("password")
    assert verify_password  # noqa: B018 — imported
    assert user["password_hash"].startswith("pbkdf2_sha256$")
    assert payload["web_auth"]["internal_token"]
    assert payload["web_auth"]["session_secret"] not in {"evileye-dev-session-secret", "change-me"}


@pytest.fixture()
def secured_client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("EVILEYE_PROTECTION_ENABLED", "1")
    monkeypatch.setenv("EVILEYE_ALLOW_PLAINTEXT_PASSWORDS", "0")
    monkeypatch.delenv("EVILEYE_ENV", raising=False)
    monkeypatch.delenv("EVILEYE_REQUIRE_AUTH", raising=False)
    bans_path = tmp_path / "web_ip_bans.json"
    reset_ip_ban_store_for_tests(bans_path)
    cfg = ProtectionConfig(
        enabled=True,
        trust_proxy=False,
        whitelist_ips=[],  # allow auto-ban of testclient host
        login_max_failures=3,
        login_window_sec=300,
        login_ban_sec=3600,
        global_max_requests=10000,
        global_window_sec=60,
        auth_fail_max=10000,
        register_max_per_window=100,
    )
    reset_rate_guard_for_tests(cfg)

    creds = {
        "web_auth": {
            "enabled": True,
            "session_secret": "test-session-secret-not-default-0123456789",
            "internal_token": "test-internal-token",
            "secure_cookies": False,
            "protection": {
                "enabled": True,
                "whitelist_ips": [],
                "login_max_failures": 3,
                "login_window_sec": 300,
                "login_ban_sec": 3600,
            },
            "users": [
                {
                    "username": "admin",
                    "password_hash": hash_password("correct-horse"),
                    "role": "admin",
                    "disabled": False,
                }
            ],
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    (tmp_path / "configs").mkdir()
    (tmp_path / "configs" / "demo.json").write_text(json.dumps({"ok": True}), encoding="utf-8")
    (tmp_path / "secrets.txt").write_text("top-secret", encoding="utf-8")

    from evileye.api.app import create_app

    app = create_app()
    # Re-apply test protection (create_app reloads from credentials)
    reset_rate_guard_for_tests(cfg)
    client = TestClient(app)
    yield client, tmp_path


def test_config_path_traversal_blocked(secured_client):
    client, _ = secured_client
    # login
    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "correct-horse"}).status_code == 200
    res = client.get("/api/v1/configs/../secrets.txt")
    assert res.status_code in {400, 404}


def test_internal_requires_token(secured_client):
    client, _ = secured_client
    res = client.post("/api/v1/internal/frames/1", content=b"jpeg")
    assert res.status_code == 401
    res_ok = client.post(
        "/api/v1/internal/frames/1",
        content=b"jpeg-bytes",
        headers={"X-EvilEye-Internal-Token": "test-internal-token"},
    )
    assert res_ok.status_code == 200


def test_login_bruteforce_autoban(secured_client):
    client, tmp_path = secured_client
    for _ in range(3):
        client.post("/api/v1/auth/login", json={"username": "admin", "password": "wrong"})
    banned = client.get("/api/v1/auth/me")
    assert banned.status_code == 403
    assert banned.json().get("detail") == "IP banned"
    assert (tmp_path / "web_ip_bans.json").exists()


def test_manual_ban_unban(secured_client):
    client, _ = secured_client
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "correct-horse"})
    assert login.status_code == 200
    created = client.post("/api/v1/bans", json={"ip": "198.51.100.9", "duration_sec": 600, "reason": "manual"})
    assert created.status_code == 200
    items = client.get("/api/v1/bans").json()["items"]
    assert any(b["ip"] == "198.51.100.9" for b in items)
    deleted = client.delete("/api/v1/bans/198.51.100.9")
    assert deleted.status_code == 200


def test_x_forwarded_for_ignored_without_trust(tmp_path, monkeypatch):
    from evileye.api.core.client_ip import resolve_client_ip

    class Req:
        client = type("C", (), {"host": "10.0.0.5"})()
        headers = {"x-forwarded-for": "203.0.113.1"}

    assert resolve_client_ip(Req(), trust_proxy=False) == "10.0.0.5"


def test_x_forwarded_for_trusted_proxy_picks_client():
    from evileye.api.core.client_ip import resolve_client_ip

    class Req:
        client = type("C", (), {"host": "10.0.0.1"})()
        headers = {"x-forwarded-for": "203.0.113.9, 10.0.0.1"}

    assert resolve_client_ip(Req(), trust_proxy=True, trusted_proxy_ips=["10.0.0.1"]) == "203.0.113.9"


def test_whitelist_skips_autoban(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = reset_ip_ban_store_for_tests(tmp_path / "web_ip_bans.json")
    cfg = ProtectionConfig(
        enabled=True,
        whitelist_ips=["testclient"],
        login_max_failures=2,
        login_window_sec=300,
        login_ban_sec=600,
    )
    guard = reset_rate_guard_for_tests(cfg)

    class Req:
        client = type("C", (), {"host": "testclient"})()
        headers = {}

    assert guard.record_login_failure(Req()) is False
    assert guard.record_login_failure(Req()) is False
    assert guard.record_login_failure(Req()) is False
    assert store.is_banned("testclient") is False
    assert store.list_bans() == []

def test_register_flood_autoban(secured_client):
    client, tmp_path = secured_client
    from evileye.api.core.rate_guard import ProtectionConfig, reset_rate_guard_for_tests

    reset_rate_guard_for_tests(
        ProtectionConfig(
            enabled=True,
            whitelist_ips=[],
            register_max_per_window=3,
            register_window_sec=600,
            register_ban_sec=600,
            global_max_requests=10000,
            auth_fail_max=10000,
            login_max_failures=100,
        )
    )
    for i in range(3):
        client.post(
            "/api/v1/auth/register",
            json={"email": f"u{i}@example.com", "password": "longpassword1"},
        )
    banned = client.get("/api/v1/auth/me")
    assert banned.status_code == 403
    assert (tmp_path / "web_ip_bans.json").exists()


def test_global_rps_autoban(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    reset_ip_ban_store_for_tests(tmp_path / "web_ip_bans.json")
    cfg = ProtectionConfig(
        enabled=True,
        whitelist_ips=[],
        global_max_requests=3,
        global_window_sec=60,
        global_ban_sec=600,
    )
    guard = reset_rate_guard_for_tests(cfg)

    class Req:
        client = type("C", (), {"host": "198.51.100.50"})()
        headers = {}

    assert guard.record_global_request(Req()) is False
    assert guard.record_global_request(Req()) is False
    assert guard.record_global_request(Req()) is True
    from evileye.api.core.ip_ban_store import get_ip_ban_store

    assert get_ip_ban_store().is_banned("198.51.100.50")


def test_mask_rtsp_in_config_secrets():
    from evileye.api.routes.configs import _mask_secrets

    masked = _mask_secrets(
        {"pipeline": {"sources": [{"source": "rtsp://user:secret@cam/stream", "password": "dbpass"}]}}
    )
    src = masked["pipeline"]["sources"][0]["source"]
    assert "secret" not in src
    assert "***:***@" in src
    assert masked["pipeline"]["sources"][0]["password"] == "***"


def test_internal_token_length_mismatch_is_401(secured_client):
    client, _ = secured_client
    res = client.post(
        "/api/v1/internal/frames/1",
        content=b"jpeg",
        headers={"X-EvilEye-Internal-Token": "short"},
    )
    assert res.status_code == 401


def _security_headers_client(tmp_path, monkeypatch, *, hsts_env=None, secure_cookies=True):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EVILEYE_ENV", raising=False)
    if hsts_env is None:
        monkeypatch.delenv("EVILEYE_HSTS", raising=False)
    else:
        monkeypatch.setenv("EVILEYE_HSTS", hsts_env)
    creds = {
        "web_auth": {
            "enabled": True,
            "session_secret": "test-session-secret-not-default-0123456789",
            "internal_token": "test-internal-token",
            "secure_cookies": secure_cookies,
            "users": [
                {
                    "username": "admin",
                    "password_hash": hash_password("correct-horse"),
                    "role": "admin",
                    "disabled": False,
                }
            ],
        }
    }
    (tmp_path / "credentials.json").write_text(json.dumps(creds), encoding="utf-8")
    from evileye.api.app import create_app

    return TestClient(create_app())


def test_hsts_absent_when_secure_cookies_without_flag(tmp_path, monkeypatch):
    client = _security_headers_client(tmp_path, monkeypatch, secure_cookies=True)
    res = client.get("/", follow_redirects=False)
    assert "strict-transport-security" not in {k.lower() for k in res.headers}


def test_hsts_present_when_env_set(tmp_path, monkeypatch):
    client = _security_headers_client(tmp_path, monkeypatch, hsts_env="1", secure_cookies=False)
    res = client.get("/", follow_redirects=False)
    assert res.headers.get("strict-transport-security", "").startswith("max-age=")
