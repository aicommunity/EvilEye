"""Unit tests for stack_control orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evileye.stack_control import (
    ReloadResult,
    StackState,
    discover_stack_state,
    frontend_needs_build,
    is_in_container,
    reload_web,
    should_use_managed_launch,
    stop_pipelines,
)


def test_is_in_container_env():
    with patch.dict("os.environ", {"EVILEYE_IN_CONTAINER": "1"}):
        assert is_in_container() is True


def test_should_use_managed_launch_direct_mode(tmp_path: Path):
    from evileye.site_profile import save_profile

    save_profile({"pipeline_launch": "direct"}, tmp_path)
    with patch("evileye.stack_control.pipeline_launch_mode", return_value="direct"):
        assert should_use_managed_launch(tmp_path) is False


def test_should_use_managed_launch_auto_active_service(tmp_path: Path):
    with patch("evileye.stack_control.pipeline_launch_mode", return_value="auto"), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=True
    ):
        assert should_use_managed_launch(tmp_path) is True


def test_stop_pipelines_hold_sets_markers(tmp_path: Path):
    (tmp_path / "monitor").mkdir(parents=True)
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={}), patch(
        "evileye.watchdog_native.set_manual_stop_cooldown"
    ) as hold, patch("evileye.watchdog_native.set_restart_grace") as grace, patch(
        "evileye.watchdog_native.find_cli_and_child", return_value=(None, None)
    ), patch("evileye.watchdog_native.stop_evileye_run_scope"):
        result = stop_pipelines(site_dir=tmp_path, stop_all=True, hold=True)
    hold.assert_called_once()
    grace.assert_called_once()
    assert result.hold_applied is True


def test_reload_web_order_stops_before_restart(tmp_path: Path):
    calls: list[str] = []

    def _stop(**_kwargs):
        calls.append("stop")
        from evileye.stack_control import StopResult

        return StopResult()

    def _restart(**_kwargs):
        calls.append("restart")
        return None

    def _wait(**_kwargs):
        calls.append("wait")
        return True

    def _start(config, **kwargs):
        calls.append("start")
        from evileye.stack_control import SpawnResult

        return SpawnResult(pid=99, mode="managed", config_path=str(config))

    state = StackState(site_dir=tmp_path, in_container=False, console_runs=[{"config_path": "c.json"}])
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines", side_effect=_stop
    ), patch("evileye.stack_control.restart_web_layer", side_effect=_restart), patch(
        "evileye.stack_control.wait_web_ready", side_effect=_wait
    ), patch("evileye.stack_control.pipeline_start", side_effect=_start), patch(
        "evileye.stack_control.resolve_production_config", return_value="configs/a.json"
    ):
        result = reload_web(site_dir=tmp_path, with_pipeline=True, config="configs/a.json")
    assert result.ok is True
    assert calls == ["stop", "restart", "wait", "start"]


def test_reload_web_infers_config_from_running_pipeline(tmp_path: Path):
    state = StackState(
        site_dir=tmp_path,
        in_container=False,
        managed_runs=[{"config_path": "configs/was_running.json"}],
    )
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines"
    ), patch("evileye.stack_control.restart_web_layer"), patch(
        "evileye.stack_control.wait_web_ready", return_value=True
    ), patch("evileye.stack_control.pipeline_start") as start, patch(
        "evileye.stack_control.resolve_production_config", return_value=None
    ):
        from evileye.stack_control import SpawnResult

        start.return_value = SpawnResult(pid=42, mode="managed", config_path="configs/was_running.json")
        result = reload_web(site_dir=tmp_path, with_pipeline=True)
    assert result.ok is True
    start.assert_called_once()
    assert start.call_args.args[0] == "configs/was_running.json"


def test_reload_web_without_pipeline_flag_leaves_pipeline_alone(tmp_path: Path):
    state = StackState(
        site_dir=tmp_path,
        in_container=False,
        managed_runs=[{"config_path": "configs/was_running.json"}],
    )
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines"
    ) as stop, patch("evileye.stack_control.restart_web_layer"), patch(
        "evileye.stack_control.wait_web_ready", return_value=True
    ), patch("evileye.stack_control.pipeline_start") as start:
        result = reload_web(site_dir=tmp_path)
    assert result.ok is True
    stop.assert_not_called()
    start.assert_not_called()


def test_reload_web_container_returns_error(tmp_path: Path):
    from evileye.stack_control import ContainerOperationError

    state = StackState(site_dir=tmp_path, in_container=True)
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines"
    ), patch(
        "evileye.stack_control.restart_web_layer",
        side_effect=ContainerOperationError("docker"),
    ):
        result = reload_web(site_dir=tmp_path)
    assert result.ok is False
    assert "docker" in result.message.lower()


def test_discover_stack_state_basic(tmp_path: Path):
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={}), patch(
        "evileye.service_manager.load_state", return_value={"installed": False}
    ), patch("evileye.service_manager.is_web_os_service_enabled", return_value=False), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=False
    ), patch("evileye.service_manager.probe_port_scheme", return_value="closed"), patch(
        "evileye.watchdog_native.manual_stop_active", return_value=False
    ), patch("evileye.watchdog_native.restart_grace_active", return_value=False), patch(
        "evileye.stack_control.is_in_container", return_value=False
    ), patch("evileye.stack_control._port_listener_pid", return_value=None), patch(
        "evileye.stack_control.find_pids_by_cmdline_regex", return_value=[]
    ), patch("evileye.site_profile.resolve_watchdog_config", return_value=None), patch(
        "evileye.site_profile.service_port", return_value=8181
    ):
        state = discover_stack_state(tmp_path)
    assert state.port == 8181
    assert state.suggested_command == "evileye dev server"


def test_frontend_needs_build_missing_static():
    with patch("evileye.setup_web.static_dir") as static_dir, patch(
        "evileye.setup_web.frontend_dir"
    ) as frontend_dir:
        static = MagicMock()
        static.__truediv__ = lambda self, key: MagicMock(is_file=lambda: False)
        static_dir.return_value = static
        frontend_dir.return_value = MagicMock()
        assert frontend_needs_build() is True
