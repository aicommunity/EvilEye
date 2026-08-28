from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from evileye.cli import app
from evileye.service_manager import ServiceActionResult


runner = CliRunner()


def test_service_install_dry_run_no_tls(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("evileye.cli_commands.web.ensure_web_environment_for_server", lambda: None)
    result = runner.invoke(app, ["service", "install", "--dry-run", "--user", "--no-tls"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "configs" / "system.json").exists()
    assert "[Unit]" in result.output or "Service installed" in result.output


def test_service_uninstall_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _fake_uninstall(**kwargs):
        return ServiceActionResult(ok=True, message="EvilEye service is not installed.", state={})

    with patch("evileye.service_manager.uninstall_service", _fake_uninstall):
        result = runner.invoke(app, ["service", "uninstall"])
    assert result.exit_code == 0, result.output
    assert "not installed" in result.output.lower()


def test_legacy_install_server_command_removed():
    result = runner.invoke(app, ["install-server", "--help"])
    assert result.exit_code != 0


def test_legacy_setup_web_command_removed():
    result = runner.invoke(app, ["setup-web", "--help"])
    assert result.exit_code != 0
