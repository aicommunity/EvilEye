from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from evileye.cli import app
from evileye.service_manager import ServiceActionResult


runner = CliRunner()


def test_service_install_dry_run(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["service-install", "--dry-run", "--user"])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "configs" / "system.json").exists()
    assert "[Unit]" in result.output or "Service installed" in result.output


def test_service_uninstall_when_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def _fake_uninstall(**kwargs):
        return ServiceActionResult(ok=True, message="EvilEye service is not installed.", state={})

    with patch("evileye.service_manager.uninstall_service", _fake_uninstall):
        result = runner.invoke(app, ["service-uninstall"])
    assert result.exit_code == 0, result.output
    assert "not installed" in result.output.lower()
