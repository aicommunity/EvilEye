"""Stage 2: builder access (B2), cross-origin admin writes (CSRF) and password confirmation."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from tests.unit.api.test_security_hardening import secured_client  # noqa: F401  (fixture)

CATALOG = "/api/v1/admin/extensions/catalog"
LOGIN = {"username": "admin", "password": "correct-horse"}


def _set_protection(tmp_path, **values):
    path = tmp_path / "credentials.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["web_auth"]["protection"].update(values)
    path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.fixture(autouse=True)
def _fresh_password_limiter():
    from evileye.api.routes import extensions as routes

    routes.reset_password_limiter_for_tests()
    yield
    routes.reset_password_limiter_for_tests()


@pytest.fixture()
def loopback(secured_client, monkeypatch):  # noqa: F811
    """A client whose TCP peer is 127.0.0.1, like a reverse proxy on the same host."""
    client, tmp_path = secured_client
    monkeypatch.delenv("EVILEYE_BUILDER_LOCALHOST_ONLY", raising=False)
    local = TestClient(client.app, client=("127.0.0.1", 50000))
    assert local.post("/api/v1/auth/login", json=LOGIN).status_code == 200
    return local, tmp_path


def test_direct_loopback_peer_may_use_builder(loopback):
    local, _ = loopback
    assert local.get(CATALOG).status_code == 200


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Forwarded-For": "203.0.113.9"},
        {"X-Real-IP": "203.0.113.9"},
        {"Forwarded": "for=203.0.113.9"},
        {"X-Forwarded-For": "127.0.0.1"},
    ],
)
def test_proxied_request_is_rejected_when_proxy_is_not_trusted(loopback, headers):
    local, _ = loopback
    response = local.get(CATALOG, headers=headers)
    assert response.status_code == 403
    assert "proxied" in response.json()["detail"]


def test_trusted_proxy_forwards_real_client_and_allowlist_decides(loopback):
    local, tmp_path = loopback
    _set_protection(
        tmp_path,
        trust_proxy=True,
        trusted_proxy_ips=["127.0.0.1"],
        builder_allowed_ips=["203.0.113.0/24", "2001:db8::1"],
    )
    assert local.get(CATALOG, headers={"X-Forwarded-For": "203.0.113.9"}).status_code == 200
    assert local.get(CATALOG, headers={"X-Forwarded-For": "198.51.100.1"}).status_code == 403
    # Loopback client behind the trusted proxy is still local.
    assert local.get(CATALOG, headers={"X-Forwarded-For": "127.0.0.1"}).status_code == 200


def test_builder_allowlist_does_not_open_direct_access_for_others(secured_client, monkeypatch):  # noqa: F811
    client, tmp_path = secured_client
    monkeypatch.delenv("EVILEYE_BUILDER_LOCALHOST_ONLY", raising=False)
    _set_protection(tmp_path, builder_allowed_ips=["203.0.113.0/24"])
    outsider = TestClient(client.app, client=("198.51.100.7", 50000))
    assert outsider.post("/api/v1/auth/login", json=LOGIN).status_code == 200
    assert outsider.get(CATALOG).status_code == 403
    allowed = TestClient(client.app, client=("203.0.113.5", 50000))
    assert allowed.post("/api/v1/auth/login", json=LOGIN).status_code == 200
    assert allowed.get(CATALOG).status_code == 200


def test_protection_config_is_cached_until_credentials_change(loopback, monkeypatch):
    from evileye.api.routes import extensions as routes

    local, tmp_path = loopback
    reads = []
    original = routes.load_protection_config

    def counting(section):
        reads.append(1)
        return original(section)

    monkeypatch.setattr(routes, "load_protection_config", counting)
    routes._protection_cache.clear()
    for _ in range(3):
        assert local.get(CATALOG).status_code == 200
    assert len(reads) == 1
    _set_protection(tmp_path, builder_allowed_ips=["203.0.113.0/24"])
    assert local.get(CATALOG).status_code == 200
    assert len(reads) == 2


def test_cross_origin_admin_write_is_rejected(loopback):
    local, _ = loopback
    body = {"config": {}}
    url = "/api/v1/admin/extensions/preview"
    evil = local.post(url, json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    assert "Cross-origin" in evil.json()["detail"]
    assert local.post(url, json=body, headers={"Referer": "https://evil.example/page"}).status_code == 403
    assert local.post(url, json=body, headers={"Origin": "null"}).status_code == 403
    assert local.post(url, json=body, headers={"Origin": "http://testserver"}).status_code != 403
    assert local.post(url, json=body, headers={"Origin": "https://ui.example", "X-Forwarded-Host": "ui.example"}).status_code != 403
    assert local.post(url, json=body).status_code != 403  # non-browser client without Origin


def test_cross_origin_reads_are_not_blocked_by_csrf_check(loopback):
    local, _ = loopback
    assert local.get(CATALOG, headers={"Origin": "https://evil.example"}).status_code == 200


def test_plugin_creation_requires_password_confirmation(loopback, monkeypatch):
    from evileye.api.routes import extensions as routes

    local, _ = loopback
    created = []
    monkeypatch.setattr(routes, "create_plugin_operation", lambda name, template: created.append(name) or {"id": "x"})
    url = "/api/v1/admin/extensions/plugins"

    assert local.post(url, json={"name": "demo", "template": "processor"}).status_code == 422
    wrong = local.post(url, json={"name": "demo", "template": "processor", "password": "nope"})
    assert wrong.status_code == 403 and created == []
    ok = local.post(url, json={"name": "demo", "template": "processor", "password": "correct-horse"})
    assert ok.status_code == 200 and created == ["demo"]


def test_disable_plugin_endpoint_persists_state(loopback, monkeypatch):
    local, tmp_path = loopback
    url = "/api/v1/admin/extensions/plugins/sample-plugin/disabled"

    response = local.post(url, json={"disabled": True})

    assert response.status_code == 200
    assert response.json()["restart_required"] is True
    state = tmp_path / "plugins" / ".evileye" / "disabled_plugins.json"
    assert json.loads(state.read_text(encoding="utf-8")) == ["sample-plugin"]
    assert local.post("/api/v1/admin/extensions/plugins/bad name!/disabled", json={"disabled": True}).status_code == 400
    assert local.post(url, json={"disabled": False}).status_code == 200
    assert json.loads(state.read_text(encoding="utf-8")) == []


def test_extension_handlers_run_in_the_threadpool():
    import inspect

    from evileye.api.routes import extensions as routes

    for name in (
        "get_extension_catalog", "preview_pipeline_config", "save_pipeline_config", "create_plugin",
        "get_extension_operation", "list_extension_operations", "download_plugin_archive",
        "set_plugin_disabled_state",
    ):
        assert not inspect.iscoroutinefunction(getattr(routes, name)), name
