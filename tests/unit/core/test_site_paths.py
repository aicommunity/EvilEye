from __future__ import annotations

import json

from evileye.controller.controller import Controller
from evileye.core.paths import creds_path, pin_site_root


def test_controller_loads_credentials_from_launch_site_after_config_chdir(
    tmp_path, monkeypatch
):
    site = tmp_path / "site"
    external_config_dir = tmp_path / "developer-config"
    site.mkdir()
    external_config_dir.mkdir()
    credentials = {"sources": {"rtsp://camera": {"username": "camera-user", "password": "test-only"}}}
    (site / "credentials.json").write_text(json.dumps(credentials), encoding="utf-8")

    monkeypatch.delenv("EVILEYE_SITE_DIR", raising=False)
    monkeypatch.chdir(site)
    assert pin_site_root() == site.resolve()
    monkeypatch.chdir(external_config_dir)

    controller = Controller.__new__(Controller)
    controller._load_credentials()

    assert creds_path() == site.resolve() / "credentials.json"
    assert controller.credentials_loaded is True
    assert controller.credentials == credentials


def test_controller_handles_missing_site_credentials(tmp_path, monkeypatch):
    site = tmp_path / "empty-site"
    site.mkdir()
    monkeypatch.setenv("EVILEYE_SITE_DIR", str(site))
    monkeypatch.chdir(tmp_path)

    controller = Controller.__new__(Controller)
    controller._load_credentials()

    assert controller.credentials_loaded is False
    assert controller.credentials == {}
