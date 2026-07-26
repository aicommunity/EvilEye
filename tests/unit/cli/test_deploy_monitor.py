"""Tests for `evileye deploy` site scaffolding (including monitor assets)."""

from __future__ import annotations

import os
from pathlib import Path

from typer.testing import CliRunner

from evileye.cli import app, _monitor_source_dir


runner = CliRunner()


def test_monitor_source_dir_resolves():
    src = _monitor_source_dir()
    assert (src / "scripts" / "install_timer.sh").is_file()
    assert (src / "scripts" / "health_check.sh").is_file()
    assert (src / "systemd" / "evileye-watchdog.service").is_file()


def test_deploy_creates_monitor_without_starting_services(tmp_path: Path):
    prev = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = runner.invoke(app, ["deploy"])
    finally:
        os.chdir(prev)

    assert result.exit_code == 0, result.output
    assert (tmp_path / "credentials.json").is_file()
    assert (tmp_path / "configs").is_dir()
    assert (tmp_path / "logs").is_dir()

    monitor = tmp_path / "monitor"
    assert (monitor / "scripts" / "install_timer.sh").is_file()
    assert (monitor / "scripts" / "health_check.sh").is_file()
    assert (monitor / "scripts" / "restart_evileye.sh").is_file()
    assert (monitor / "systemd" / "evileye-watchdog.service").is_file()
    assert (monitor / "incidents").is_dir()
    assert (monitor / "reports").is_dir()
    assert (monitor / "INSTALL_HINT.txt").is_file()

    hint = (monitor / "INSTALL_HINT.txt").read_text(encoding="utf-8")
    assert "NOT started automatically" in hint
    assert "install_timer.sh" in hint

    # Deploy must not enable user systemd units.
    assert "systemctl" not in result.output.lower() or "not enabled" in result.output.lower()
    unit_text = (monitor / "systemd" / "evileye-watchdog.service").read_text(encoding="utf-8")
    assert "KillMode=process" in unit_text


def test_deploy_updates_monitor_scripts_on_rerun(tmp_path: Path):
    prev = Path.cwd()
    try:
        os.chdir(tmp_path)
        assert runner.invoke(app, ["deploy"]).exit_code == 0
        marker = tmp_path / "monitor" / "scripts" / "health_check.sh"
        marker.write_text("# stale\n", encoding="utf-8")
        assert runner.invoke(app, ["deploy"]).exit_code == 0
    finally:
        os.chdir(prev)

    text = (tmp_path / "monitor" / "scripts" / "health_check.sh").read_text(encoding="utf-8")
    assert text.startswith("#!/")
    assert "# stale" not in text
