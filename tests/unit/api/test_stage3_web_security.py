"""Stage-3 audit fixes: parameterized journal SQL, setup SSRF/path guards."""

from __future__ import annotations

import json


class TestJournalSqlParameterized:
    def _make_source(self, tmp_path):
        from evileye.visualization_modules.journal_data_source_db import (
            DatabaseJournalDataSource,
        )

        class _Db:
            def get_params(self):
                return {"image_dir": str(tmp_path), "preview_width": 300, "preview_height": 150}

            def get_cameras_params(self):
                return []

            def query(self, sql, data=None):
                raise AssertionError("query must not be called by builders here")

        source = DatabaseJournalDataSource(_Db(), journal_type="objects")
        source.set_date("2026-11-21")
        return source

    def test_objects_sql_uses_placeholders(self, tmp_path):
        source = self._make_source(tmp_path)
        sql, params = source._build_objects_sql(
            {"source_id": "3", "object_id": "9"}, include_pagination=True, page=2, size=25
        )
        # Values must travel as parameters, never interpolated (audit W1).
        assert "'2026-11-21'" not in sql
        assert "%s" in sql
        assert "2026-11-21" in params
        assert 3 in params and 9 in params  # int-cast ids
        assert 25 in params and 50 in params  # LIMIT/OFFSET as params

    def test_source_name_in_filter_uses_placeholders(self, tmp_path):
        source = self._make_source(tmp_path)
        sql, params = source._build_objects_sql(
            {"source_names": ["Cam1", "Cam'2"]}, include_pagination=False
        )
        assert sql.count("%s") >= 3  # date + two names
        assert "Cam'2" in params  # raw value, no manual escaping needed

    def test_events_sql_uses_placeholders(self, tmp_path):
        source = self._make_source(tmp_path)

        class _Adapter:
            def select_query(self):
                return "SELECT time_stamp, source_name FROM zone_events"

        source.adapters = [_Adapter()]
        sql, params = source._build_events_sql({}, include_pagination=True, page=0, size=10)
        assert "%s" in sql and len(params) >= 2


class TestSetupGuards:
    def _client(self, tmp_path, monkeypatch):
        from evileye.api.app import create_app
        from fastapi.testclient import TestClient

        monkeypatch.chdir(tmp_path)
        (tmp_path / "credentials.json").write_text(
            json.dumps({"web_auth": {"enabled": True, "users": []}}), encoding="utf-8"
        )
        import os

        monkeypatch.setenv("EVILEYE_BOOTSTRAP_ADMIN_PASSWORD", "admin")
        from evileye.api.core.web_auth_bootstrap import ensure_default_admin_credentials

        ensure_default_admin_credentials(tmp_path / "credentials.json")
        app = create_app()
        client = TestClient(app)
        login = client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "admin"}
        )
        assert login.status_code == 200
        client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "admin", "new_password": "admin-secret-123"},
        )
        return client

    def test_test_database_rejects_link_local_host(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        resp = client.post(
            "/api/v1/setup/test-database",
            json={"host_name": "169.254.169.254", "port": 80},
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "not allowed" in resp.json()["message"]

    def test_test_database_allows_localhost(self, tmp_path, monkeypatch):
        client = self._client(tmp_path, monkeypatch)
        resp = client.post(
            "/api/v1/setup/test-database",
            json={"host_name": "localhost", "port": 59999},
        )
        assert resp.status_code == 200
        # Connection fails (no server) but the host itself is permitted.
        assert "not allowed" not in str(resp.json().get("message", ""))

    def test_check_data_dir_rejects_paths_outside_site_root(self, tmp_path, monkeypatch):
        import sys

        if sys.platform == "win32":
            outside = "Z:\\evileye\\definitely\\outside"
        else:
            outside = "/evileye/definitely/outside"
        client = self._client(tmp_path, monkeypatch)
        resp = client.post("/api/v1/setup/check-data-dir", json={"path": outside})
        assert resp.status_code == 200
        assert resp.json()["ok"] is False
        assert "site root" in resp.json()["message"]
