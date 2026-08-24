from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from evileye.cli import app
from evileye.service_manager import ServiceActionResult


runner = CliRunner()


def test_install_server_dry_run_no_tls(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("evileye.cli._ensure_web_environment_for_server", lambda: None)
    result = runner.invoke(app, ["install-server", "--dry-run", "--user", "--no-tls"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "configs" / "system.json").exists()
    assert "[Unit]" in result.output or "Service installed" in result.output


def test_uninstall_server_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _fake_uninstall(**kwargs):
        return ServiceActionResult(ok=True, message="EvilEye service is not installed.", state={})

    with patch("evileye.service_manager.uninstall_service", _fake_uninstall):
        result = runner.invoke(app, ["uninstall-server"])
    assert result.exit_code == 0, result.output
    assert "not installed" in result.output.lower()


def test_old_service_install_command_removed():
    result = runner.invoke(app, ["service-install", "--help"])
    assert result.exit_code != 0
    result = runner.invoke(app, ["service-uninstall", "--help"])
    assert result.exit_code != 0
