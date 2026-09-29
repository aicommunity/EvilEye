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
    ), patch("evileye.watchdog_native.stop_evileye_run_scope") as scope_stop:
        result = stop_pipelines(site_dir=tmp_path, stop_all=True, hold=True)
    hold.assert_called_once()
    grace.assert_called_once()
    scope_stop.assert_called_once_with(stop_all=True)
    assert result.hold_applied is True


def test_stop_pipelines_grace_suppress_skips_manual(tmp_path: Path):
    (tmp_path / "monitor").mkdir(parents=True)
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={}), patch(
        "evileye.watchdog_native.set_manual_stop_cooldown"
    ) as hold, patch("evileye.watchdog_native.set_restart_grace") as grace, patch(
        "evileye.watchdog_native.find_cli_and_child", return_value=(None, None)
    ), patch("evileye.watchdog_native.stop_evileye_run_scope") as scope_stop:
        result = stop_pipelines(
            site_dir=tmp_path, config="configs/a.json", watchdog_suppress="grace"
        )
    hold.assert_not_called()
    grace.assert_called_once()
    scope_stop.assert_called_once_with(config="configs/a.json")
    assert result.hold_applied is True


def test_reload_web_order_stops_before_restart(tmp_path: Path):
    calls: list[str] = []
    stop_kwargs: list[dict] = []

    def _stop(**kwargs):
        calls.append("stop")
        stop_kwargs.append(kwargs)
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
    assert stop_kwargs[0].get("watchdog_suppress") == "grace"


def test_reload_web_respects_release_hold_false(tmp_path: Path):
    state = StackState(site_dir=tmp_path, in_container=False)
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines"
    ), patch("evileye.stack_control.restart_web_layer"), patch(
        "evileye.stack_control.wait_web_ready", return_value=True
    ), patch("evileye.stack_control.pipeline_start") as start, patch(
        "evileye.stack_control.resolve_pipeline_config", return_value="configs/a.json"
    ):
        from evileye.stack_control import SpawnResult

        start.return_value = SpawnResult(pid=1, mode="managed", config_path="configs/a.json")
        result = reload_web(
            site_dir=tmp_path, with_pipeline=True, config="configs/a.json", release_hold=False
        )
    assert result.ok is True
    assert start.call_args.kwargs.get("release_hold") is False


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
        "evileye.stack_control.resolve_pipeline_config",
        return_value="configs/was_running.json",
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


def test_pipeline_restart_uses_replace_and_waits_for_alive(tmp_path: Path):
    from evileye.stack_control import SpawnResult, pipeline_restart

    spawn = SpawnResult(pid=1234, mode="managed", config_path="configs/a.json")
    with patch("evileye.stack_control.stop_pipelines") as stop, patch(
        "evileye.stack_control.pipeline_start", return_value=spawn
    ) as start, patch("evileye.stack_control._wait_pipeline_alive") as wait_alive, patch(
        "evileye.stack_control.time.sleep"
    ), patch("evileye.watchdog_native.clear_manual_stop_cooldown") as clear_hold:
        result = pipeline_restart("configs/a.json", site_dir=tmp_path, hold=False)

    stop.assert_called_once()
    assert stop.call_args.kwargs.get("watchdog_suppress") == "none"
    start.assert_called_once()
    assert start.call_args.kwargs.get("replace") is True
    assert start.call_args.kwargs.get("release_hold") is True
    clear_hold.assert_called_once()
    wait_alive.assert_called_once_with(1234)
    assert result.pid == 1234


def test_pipeline_restart_hold_grace_not_manual(tmp_path: Path):
    from evileye.stack_control import SpawnResult, pipeline_restart

    spawn = SpawnResult(pid=55, mode="managed", config_path="configs/a.json")
    with patch("evileye.stack_control.stop_pipelines") as stop, patch(
        "evileye.stack_control.pipeline_start", return_value=spawn
    ), patch("evileye.stack_control._wait_pipeline_alive"), patch(
        "evileye.stack_control.time.sleep"
    ), patch("evileye.watchdog_native.clear_manual_stop_cooldown"):
        pipeline_restart("configs/a.json", site_dir=tmp_path, hold=True)

    assert stop.call_args.kwargs.get("watchdog_suppress") == "grace"
    assert stop.call_args.kwargs.get("hold") is not True


def test_spawn_direct_systemd_run_includes_no_block(tmp_path: Path):
    from evileye.stack_control import spawn_direct_pipeline

    cfg = tmp_path / "configs" / "cam.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{}", encoding="utf-8")
    (tmp_path / "monitor").mkdir(parents=True)

    mock_run = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("evileye.stack_control.should_use_managed_launch", return_value=False), patch(
        "evileye.stack_control.gui_default", return_value=False
    ), patch("evileye.stack_control.shutil.which", side_effect=lambda n: "/bin/systemd-run" if n == "systemd-run" else None), patch(
        "evileye.stack_control.sys.platform", "linux"
    ), patch("evileye.stack_control.subprocess.run", mock_run), patch(
        "evileye.watchdog_native.stop_evileye_run_scope"
    ), patch(
        "evileye.stack_control._poll_cli_or_child_pid", return_value=4242
    ):
        result = spawn_direct_pipeline(str(cfg), site_dir=tmp_path, detach=True, gui=False)

    assert result.mode == "direct-detach"
    assert result.pid == 4242
    argv = mock_run.call_args.args[0]
    assert "--no-block" in argv
    assert "--collect" in argv
    assert any(a.startswith("--unit=evileye-run-cam") for a in argv)


def test_spawn_direct_foreground_waits(tmp_path: Path):
    from evileye.stack_control import spawn_direct_pipeline

    cfg = tmp_path / "configs" / "cam.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("{}", encoding="utf-8")

    mock_run = MagicMock(return_value=MagicMock(returncode=7))
    with patch("evileye.stack_control.gui_default", return_value=False), patch(
        "evileye.stack_control.subprocess.run", mock_run
    ) as run, patch("evileye.stack_control.subprocess.Popen") as popen:
        result = spawn_direct_pipeline(str(cfg), site_dir=tmp_path, detach=False, gui=False)

    popen.assert_not_called()
    run.assert_called_once()
    assert result.mode == "direct-foreground"
    assert result.exit_code == 7


def test_wait_pipeline_alive_raises_when_process_dies():
    from evileye.stack_control import _wait_pipeline_alive

    with patch("evileye.stack_control.pid_exists", return_value=False):
        with pytest.raises(RuntimeError, match="exited immediately"):
            _wait_pipeline_alive(999)


def test_scope_unit_name_for_config():
    from evileye.watchdog_native import config_scope_stem, scope_unit_name_for_config

    assert config_scope_stem("configs/Poly Cameras.json") == "poly-cameras"
    assert scope_unit_name_for_config("configs/a.json") == "evileye-run-a"


def test_stop_evileye_run_scope_by_config():
    from evileye.watchdog_native import stop_evileye_run_scope

    with patch("evileye.watchdog_native.sys.platform", "linux"), patch(
        "evileye.watchdog_native.shutil.which", return_value="/bin/systemctl"
    ), patch("evileye.watchdog_native.subprocess.run") as run:
        stop_evileye_run_scope(config="configs/cam.json")
    units = [c.args[0][3] for c in run.call_args_list]
    assert "evileye-run-cam.scope" in units


def test_stop_evileye_run_scope_stop_all_includes_legacy():
    from evileye.watchdog_native import stop_evileye_run_scope

    with patch("evileye.watchdog_native.sys.platform", "linux"), patch(
        "evileye.watchdog_native.shutil.which", return_value="/bin/systemctl"
    ), patch(
        "evileye.watchdog_native._list_evileye_run_scopes",
        return_value=["evileye-run-a.scope"],
    ), patch("evileye.watchdog_native.subprocess.run") as run:
        stop_evileye_run_scope(stop_all=True)
    stopped = {c.args[0][3] for c in run.call_args_list if c.args[0][2] == "stop"}
    assert "evileye-run-a.scope" in stopped
    assert "evileye-run.scope" in stopped