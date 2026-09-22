"""Unit tests for pipeline config resolve and status suggestions."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from evileye.stack_control import (
    AmbiguousPipelineConfigError,
    COMMAND_CATALOG,
    StackState,
    discover_stack_state,
    require_pipeline_config,
    resolve_pipeline_config,
    stack_state_to_json,
)


def test_resolve_pipeline_config_explicit(tmp_path: Path):
    assert (
        resolve_pipeline_config(tmp_path, explicit="configs/a.json", allow_running=True)
        == "configs/a.json"
    )


def test_resolve_pipeline_config_unique_running(tmp_path: Path):
    with patch(
        "evileye.stack_control._alive_pipeline_configs",
        return_value=["/site/configs/a.json"],
    ), patch("evileye.site_profile.resolve_production_config", return_value=None):
        assert resolve_pipeline_config(tmp_path, allow_running=True) == "/site/configs/a.json"


def test_resolve_pipeline_config_profile_when_no_running(tmp_path: Path):
    with patch("evileye.stack_control._alive_pipeline_configs", return_value=[]), patch(
        "evileye.stack_control.resolve_production_config", return_value="configs/prod.json"
    ):
        assert resolve_pipeline_config(tmp_path, allow_running=True) == "configs/prod.json"


def test_resolve_pipeline_config_start_skips_running(tmp_path: Path):
    with patch(
        "evileye.stack_control._alive_pipeline_configs",
        return_value=["/site/configs/running.json"],
    ), patch(
        "evileye.stack_control.resolve_production_config", return_value="configs/prod.json"
    ):
        assert (
            resolve_pipeline_config(tmp_path, allow_running=False) == "configs/prod.json"
        )


def test_resolve_pipeline_config_multi_run_raises(tmp_path: Path):
    with patch(
        "evileye.stack_control._alive_pipeline_configs",
        return_value=["configs/a.json", "configs/b.json"],
    ):
        with pytest.raises(AmbiguousPipelineConfigError, match="Multiple pipeline"):
            resolve_pipeline_config(tmp_path, allow_running=True)


def test_require_pipeline_config_missing(tmp_path: Path):
    with patch("evileye.stack_control._alive_pipeline_configs", return_value=[]), patch(
        "evileye.site_profile.resolve_production_config", return_value=None
    ), patch("evileye.site_profile.resolve_watchdog_config", return_value=None):
        with pytest.raises(FileNotFoundError, match="production_config"):
            require_pipeline_config(tmp_path, allow_running=True)


def test_discover_suggested_prefers_duplicate_over_default(tmp_path: Path):
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={}), patch(
        "evileye.service_manager.load_state", return_value={"installed": True}
    ), patch("evileye.service_manager.is_web_os_service_enabled", return_value=True), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=True
    ), patch("evileye.service_manager.probe_port_scheme", return_value="http"), patch(
        "evileye.watchdog_native.manual_stop_active", return_value=False
    ), patch("evileye.watchdog_native.restart_grace_active", return_value=False), patch(
        "evileye.stack_control.is_in_container", return_value=False
    ), patch("evileye.stack_control._port_listener_pid", return_value=1), patch(
        "evileye.stack_control.find_pids_by_cmdline_regex", return_value=[]
    ), patch("evileye.site_profile.resolve_watchdog_config", return_value=None), patch(
        "evileye.site_profile.service_port", return_value=8181
    ), patch(
        "evileye.site_runtime_guard.singleton_warnings",
        return_value=["duplicate_pipeline_detected:a.json pids=1,2"],
    ):
        state = discover_stack_state(tmp_path)
    assert state.suggested_command == "evileye pipeline stop --all"
    assert state.suggested_commands[0] == "evileye pipeline stop --all"


def test_discover_suggested_web_collision(tmp_path: Path):
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={}), patch(
        "evileye.service_manager.load_state", return_value={"installed": True}
    ), patch("evileye.service_manager.is_web_os_service_enabled", return_value=True), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=True
    ), patch("evileye.service_manager.probe_port_scheme", return_value="http"), patch(
        "evileye.watchdog_native.manual_stop_active", return_value=False
    ), patch("evileye.watchdog_native.restart_grace_active", return_value=False), patch(
        "evileye.stack_control.is_in_container", return_value=False
    ), patch("evileye.stack_control._port_listener_pid", return_value=1), patch(
        "evileye.stack_control.find_pids_by_cmdline_regex", return_value=[]
    ), patch("evileye.site_profile.resolve_watchdog_config", return_value=None), patch(
        "evileye.site_profile.service_port", return_value=8181
    ), patch(
        "evileye.site_runtime_guard.singleton_warnings",
        return_value=["web_collision:service_active+foreground_pids=9"],
    ):
        state = discover_stack_state(tmp_path)
    assert state.suggested_command == "evileye service restart"


def test_stack_state_to_json_includes_catalog_and_suggestions(tmp_path: Path):
    state = StackState(
        site_dir=tmp_path,
        in_container=False,
        suggested_command="evileye reload web",
        suggested_commands=["evileye pipeline stop --all", "evileye reload web"],
    )
    data = stack_state_to_json(state)
    assert data["suggested_commands"][0] == "evileye pipeline stop --all"
    assert len(data["command_catalog"]) == len(COMMAND_CATALOG)
    assert data["command_catalog"][0]["command"] == COMMAND_CATALOG[0][0]


def test_pipeline_stop_requires_flags(tmp_path: Path):
    from typer.testing import CliRunner

    from evileye.cli_commands.pipeline import app

    runner = CliRunner()
    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 1
    assert "--config" in (result.output or "") or "--all" in (result.output or "")


def test_pipeline_restart_resolves_unique_run(tmp_path: Path):
    from typer.testing import CliRunner

    from evileye.cli_commands.pipeline import app
    from evileye.stack_control import SpawnResult

    runner = CliRunner()
    spawn = SpawnResult(pid=42, mode="managed", config_path="configs/a.json")
    with patch(
        "evileye.stack_control.require_pipeline_config", return_value="configs/a.json"
    ) as require, patch(
        "evileye.stack_control.pipeline_restart", return_value=spawn
    ) as restart:
        result = runner.invoke(app, ["restart"], catch_exceptions=False)
    assert result.exit_code == 0
    require.assert_called_once()
    assert require.call_args.kwargs.get("allow_running") is True
    restart.assert_called_once()
    assert restart.call_args.args[0] == "configs/a.json"
