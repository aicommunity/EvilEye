from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core import journal_service
from evileye.api.core.journal_grouping import group_objects_rows
from evileye.api.core.web_auth_bootstrap import ensure_default_admin_credentials
from evileye.api.routes import streaming as streaming_routes
from evileye.api.security import permissions_for_role
from evileye.controller.services.streaming_service import StreamingService


def test_user_role_permissions():
    perms = set(permissions_for_role("user"))
    assert "live:view" in perms
    assert "journal:view" in perms
    assert "logs:view" not in perms
    assert "history:view" not in perms
    assert "users:manage" not in perms


def test_admin_role_permissions():
    perms = set(permissions_for_role("admin"))
    assert "logs:view" in perms
    assert "users:manage" in perms


def test_group_objects_rows_merges_found_lost():
    rows = group_objects_rows(
        [
            {"event_type": "found", "object_id": 1, "ts": "2026-01-01", "source_name": "Cam1", "class_name": "person", "confidence": 0.9},
            {"event_type": "lost", "object_id": 1, "ts": "2026-01-02", "source_name": "Cam1"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["event"] == "ObjectEvent"
    assert "Object Id=1" in rows[0]["information"]


def test_streaming_guard_multi_source(tmp_path, monkeypatch):
    monkeypatch.setattr(
        streaming_routes,
        "get_run_summary",
        lambda rid: {"id": rid, "sources": [{"source_id": 0}, {"source_id": 1}]},
    )
    run_info = {"id": 1, "state": "running", "sources": []}
    with pytest.raises(Exception) as exc:
        streaming_routes._require_source_id_if_multi(run_info, None)
    assert exc.value.status_code == 400


def test_streaming_has_consumers_with_demand_or_local_or_server():
    """Grid/stream demand or local MJPEG enables consumers; alive server alone needs heartbeat env."""
    service = StreamingService()

    class _ServerProcessManager:
        def is_alive(self):
            return True

        def has_preview_demand(self, pipeline_key):
            return False

        def get_preview_demand_level(self, pipeline_key):
            return "idle"

    service.configure(pipeline_id="1", publish_fps=10.0, server_process_manager=_ServerProcessManager())
    assert service.has_consumers(source_id=0) is False

    class _DeadServer:
        def is_alive(self):
            return False

        def has_preview_demand(self, pipeline_key):
            return False

        def get_preview_demand_level(self, pipeline_key):
            return "idle"

    service.configure(pipeline_id="1", publish_fps=10.0, server_process_manager=_DeadServer())
    assert service.has_consumers(source_id=0) is False

    class _DemandManager(_DeadServer):
        def is_alive(self):
            return True

        def has_preview_demand(self, pipeline_key):
            return True

        def get_preview_demand_level(self, pipeline_key):
            return "grid"

    service.configure(pipeline_id="1", publish_fps=10.0, server_process_manager=_DemandManager())
    assert service.has_consumers(source_id=0) is True


def test_streaming_has_consumers_when_server_process_alive():
    test_streaming_has_consumers_with_demand_or_local_or_server()


def test_streaming_should_publish_heartbeat_vs_full(monkeypatch):
    service = StreamingService()
    service.configure(pipeline_id="1", publish_fps=10.0)
    calls = []

    def fake_throttle(key, *, fps_override=None):
        calls.append(fps_override)
        return True

    monkeypatch.setattr(service, "_throttle_ok", fake_throttle)

    monkeypatch.setattr(
        service,
        "_get_consumer_state",
        lambda _k: (False, False, True, False),
    )
    assert service._should_publish("1:0") is False
    assert calls == []

    monkeypatch.setenv("EVILEYE_PREVIEW_HEARTBEAT_FPS", "1")
    assert service._should_publish("1:0") is True
    assert calls[-1] == 1.0

    calls.clear()
    monkeypatch.setattr(
        service,
        "_get_consumer_state",
        lambda _k: (False, True, True, False),
    )
    monkeypatch.setattr(service, "_get_preview_demand_level", lambda _k: "stream")
    assert service._should_publish("1:0") is True
    assert calls[-1] == 10.0

    calls.clear()
    monkeypatch.setattr(
        service,
        "_get_consumer_state",
        lambda _k: (False, False, False, False),
    )
    assert service._should_publish("1:0") is False
    assert calls == []


def test_web_auth_bootstrap_creates_admin(tmp_path, monkeypatch):
    creds_path = tmp_path / "credentials.json"
    monkeypatch.chdir(tmp_path)
    created = ensure_default_admin_credentials(creds_path)
    assert created is True
    payload = json.loads(creds_path.read_text(encoding="utf-8"))
    users = payload["web_auth"]["users"]
    assert users[0]["username"] == "admin"
    assert users[0]["role"] == "admin"
    assert not ensure_default_admin_credentials(creds_path)


def test_journal_json_fallback_when_database_disabled(tmp_path, monkeypatch):
    base_dir = tmp_path / "EvilEyeData"
    metadata = base_dir / "Detections" / "2026-06-13" / "Metadata"
    metadata.mkdir(parents=True)
    (metadata / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 1,
                    "timestamp": "2026-06-13T10:00:00",
                    "source_id": 0,
                    "source_name": "Cam1",
                    "object_id": 42,
                    "class_name": "person",
                }
            ]
        ),
        encoding="utf-8",
    )
    config_path = tmp_path / "poly.json"
    config_path.write_text(
        json.dumps(
            {
                "controller": {"use_database": False, "image_dir": str(base_dir)},
                "pipeline": {"sources": [{"source_names": ["Cam1"], "source_ids": [0]}]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        journal_service,
        "get_current_run_summary",
        lambda: {"config_path": str(config_path)},
    )
    status = journal_service.journal_availability()
    assert status["available"] is True
    assert status["mode"] == "json"
    payload = journal_service.load_objects_grouped_page(page=0, size=10, filters={})
    assert payload["available"] is True
    assert payload["mode"] == "json"
    assert payload["total"] >= 1


def test_journal_disabled_message(tmp_path, monkeypatch):
    config_path = tmp_path / "poly.json"
    config_path.write_text(json.dumps({"controller": {"use_database": False}}), encoding="utf-8")
    monkeypatch.setattr(
        journal_service,
        "get_current_run_summary",
        lambda: {"config_path": str(config_path)},
    )
    payload = journal_service.load_events_page(page=0, size=10, filters={})
    assert payload["available"] is False
    assert payload["reason"] == "database_disabled"
    assert "use_database" in payload["message"]


def test_auth_register_and_users_flow(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps({"web_auth": {"enabled": True, "users": []}}), encoding="utf-8")
    ensure_default_admin_credentials(creds_path)

    app = create_app()
    client = TestClient(app)

    reg = client.post("/api/v1/auth/register", json={"email": "test@example.com", "password": "secret1"})
    assert reg.status_code == 200

    login_pending = client.post("/api/v1/auth/login", json={"username": "test@example.com", "password": "secret1"})
    assert login_pending.status_code == 401

    admin_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"})
    assert admin_login.status_code == 200

    approve = client.post("/api/v1/users/test@example.com/approve")
    assert approve.status_code == 200

    app.state.web_auth = __import__("evileye.api.security", fromlist=["load_web_auth_config"]).load_web_auth_config()
    user_login = client.post("/api/v1/auth/login", json={"username": "test@example.com", "password": "secret1"})
    assert user_login.status_code == 200
    perms = set(user_login.json().get("permissions") or [])
    assert "logs:view" not in perms


def test_admin_create_user_approved_and_login(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    creds_path = tmp_path / "credentials.json"
    creds_path.write_text(json.dumps({"web_auth": {"enabled": True, "users": []}}), encoding="utf-8")
    ensure_default_admin_credentials(creds_path)

    app = create_app()
    client = TestClient(app)

    assert client.post("/api/v1/users", json={
        "email": "new@example.com",
        "password": "secret12",
        "role": "user",
    }).status_code in {401, 403}

    assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin"}).status_code == 200

    created = client.post(
        "/api/v1/users",
        json={"email": "new@example.com", "password": "secret12", "role": "user"},
    )
    assert created.status_code == 200
    body = created.json()
    assert body["ok"] is True
    assert body["user"]["status"] == "approved"
    assert body["mail"]["sent"] is False

    dup = client.post(
        "/api/v1/users",
        json={"email": "new@example.com", "password": "secret12", "role": "user"},
    )
    assert dup.status_code == 409

    login = client.post("/api/v1/auth/login", json={"username": "new@example.com", "password": "secret12"})
    assert login.status_code == 200


def test_user_store_create_user_unit(tmp_path):
    from evileye.api.core.user_store import UserStore

    store = UserStore(tmp_path / "web_users.json")
    record = store.create_user("ops@example.com", "secret12", role="admin")
    assert record["status"] == "approved"
    assert record["role"] == "admin"
    assert store.authenticate("ops@example.com", "secret12") is not None
