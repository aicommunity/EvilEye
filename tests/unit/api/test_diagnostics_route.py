"""Client diagnostics ingest route + JSONL writer."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from evileye.api.app import AuthGuardMiddleware
from evileye.api.core.client_diag_log import append_client_diag_events, client_diag_path
from evileye.api.middleware.adaptive_session import AdaptiveSessionMiddleware
from evileye.api.routes import diagnostics as diagnostics_mod
from evileye.api.routes.diagnostics import router as diagnostics_router
from evileye.api.security import permissions_for_role, required_permissions_for_request


def test_append_client_diag_events_writes_jsonl(tmp_path: Path):
    n = append_client_diag_events(
        user="admin",
        session_id="s1",
        events=[{"kind": "mode_change", "payload": {"to": "error"}}],
        ua="test-agent",
        page="live",
        logs_dir=tmp_path,
    )
    assert n == 1
    path = client_diag_path(logs_dir=tmp_path)
    assert path.is_file()
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
    assert "mode_change" in lines[0]
    assert "admin" in lines[0]


def test_diagnostics_post_requires_live_view_not_admin():
    assert required_permissions_for_request("/api/v1/diagnostics/client", "POST") == {"live:view"}
    assert required_permissions_for_request("/api/v1/diagnostics/client", "GET") == {"live:view"}
    assert "live:view" in permissions_for_role("user")
    assert "system:admin" not in permissions_for_role("user")


def _diag_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(diagnostics_mod, "append_client_diag_events", lambda **kw: append_client_diag_events(**{**kw, "logs_dir": tmp_path}))
    diagnostics_mod._rate_by_user.clear()

    app = FastAPI()
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=False,
    )

    @app.post("/login")
    async def login(request: Request):
        request.session["user"] = {"username": "admin", "role": "admin"}
        return {"ok": True}

    app.include_router(diagnostics_router)
    return TestClient(app)


def _diag_client_with_auth_guard(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr(diagnostics_mod, "append_client_diag_events", lambda **kw: append_client_diag_events(**{**kw, "logs_dir": tmp_path}))
    diagnostics_mod._rate_by_user.clear()

    app = FastAPI()
    app.add_middleware(AuthGuardMiddleware)
    app.add_middleware(
        AdaptiveSessionMiddleware,
        secret_key="x" * 32,
        session_cookie="evileye_session",
        secure_cookies=False,
    )
    app.state.web_auth = SimpleNamespace(enabled=True, internal_token="")

    @app.post("/login-user")
    async def login_user(request: Request):
        request.session["user"] = {
            "username": "playback-test@example.com",
            "role": "user",
            "permissions": permissions_for_role("user"),
        }
        return {"ok": True}

    @app.post("/login-admin")
    async def login_admin(request: Request):
        request.session["user"] = {
            "username": "admin",
            "role": "admin",
            "permissions": permissions_for_role("admin"),
        }
        return {"ok": True}

    app.include_router(diagnostics_router)
    return TestClient(app)


def test_diagnostics_post_requires_auth(tmp_path: Path, monkeypatch):
    client = _diag_client(tmp_path, monkeypatch)
    res = client.post(
        "/api/v1/diagnostics/client",
        json={"session_id": "s", "events": [{"kind": "x"}]},
    )
    assert res.status_code == 401


def test_diagnostics_post_writes_for_authenticated(tmp_path: Path, monkeypatch):
    client = _diag_client(tmp_path, monkeypatch)
    assert client.post("/login").status_code == 200
    res = client.post(
        "/api/v1/diagnostics/client",
        json={
            "session_id": "sess-1",
            "page": "live",
            "events": [{"kind": "ws_close", "payload": {"code": 1006}}],
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["written"] == 1
    assert body["client_debug"] is True
    path = client_diag_path(logs_dir=tmp_path)
    assert path.is_file()


def test_diagnostics_post_user_role_passes_auth_guard(tmp_path: Path, monkeypatch):
    client = _diag_client_with_auth_guard(tmp_path, monkeypatch)
    assert client.post("/login-user").status_code == 200
    res = client.post(
        "/api/v1/diagnostics/client",
        json={"session_id": "exp", "events": [{"kind": "verify"}]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["written"] == 1
    assert client_diag_path(logs_dir=tmp_path).is_file()


def test_diagnostics_post_admin_passes_auth_guard(tmp_path: Path, monkeypatch):
    client = _diag_client_with_auth_guard(tmp_path, monkeypatch)
    assert client.post("/login-admin").status_code == 200
    res = client.post(
        "/api/v1/diagnostics/client",
        json={"session_id": "exp-admin", "events": [{"kind": "verify"}]},
    )
    assert res.status_code == 200
    assert res.json()["written"] == 1


def test_diagnostics_rate_limit(tmp_path: Path, monkeypatch):
    client = _diag_client(tmp_path, monkeypatch)
    assert client.post("/login").status_code == 200
    monkeypatch.setattr(diagnostics_mod, "_MAX_BATCHES_PER_MIN", 3)
    diagnostics_mod._rate_by_user.clear()
    payload = {"session_id": "s", "events": [{"kind": "ping"}]}
    assert client.post("/api/v1/diagnostics/client", json=payload).status_code == 200
    assert client.post("/api/v1/diagnostics/client", json=payload).status_code == 200
    assert client.post("/api/v1/diagnostics/client", json=payload).status_code == 200
    assert client.post("/api/v1/diagnostics/client", json=payload).status_code == 429
