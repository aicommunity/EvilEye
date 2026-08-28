"""Unit tests for per-site singleton launch guards."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from evileye.site_runtime_guard import (
    DuplicatePipelineError,
    EnsureResult,
    discover_site_runs,
    ensure_pipeline_singleton,
    find_alive_pipelines_for_config,
    singleton_warnings,
    spawn_lock,
)
from evileye.stack_control import pipeline_start, reload_web


def test_ensure_pipeline_singleton_fail_when_alive(tmp_path: Path):
    alive = [{"pid": 4242, "config_path": "configs/a.json", "managed": True, "alive": True}]
    with patch(
        "evileye.site_runtime_guard.find_alive_pipelines_for_config",
        return_value=alive,
    ):
        with pytest.raises(DuplicatePipelineError, match="pid=4242"):
            ensure_pipeline_singleton("configs/a.json", tmp_path, policy="fail")


def test_ensure_pipeline_singleton_skip(tmp_path: Path):
    alive = [{"pid": 4242, "config_path": "configs/a.json", "managed": True}]
    with patch(
        "evileye.site_runtime_guard.find_alive_pipelines_for_config",
        return_value=alive,
    ):
        result = ensure_pipeline_singleton("configs/a.json", tmp_path, policy="skip")
    assert result.skipped is True
    assert result.existing_pid == 4242


def test_ensure_pipeline_singleton_replace_stops_first(tmp_path: Path):
    alive = [{"pid": 4242, "config_path": "configs/a.json", "managed": True}]
    with patch(
        "evileye.site_runtime_guard.find_alive_pipelines_for_config",
        return_value=alive,
    ), patch("evileye.stack_control.stop_pipelines") as stop:
        result = ensure_pipeline_singleton("configs/a.json", tmp_path, policy="replace")
    stop.assert_called_once()
    assert result.replaced is True


def test_pipeline_start_fail_without_replace(tmp_path: Path):
    from contextlib import contextmanager

    @contextmanager
    def noop_lock(_site):
        yield

    with patch("evileye.stack_control._resolve_site", return_value=tmp_path), patch(
        "evileye.site_runtime_guard.spawn_lock", noop_lock
    ), patch(
        "evileye.site_runtime_guard.ensure_pipeline_singleton",
        side_effect=DuplicatePipelineError("already running", pid=99),
    ):
        with pytest.raises(DuplicatePipelineError):
            pipeline_start("configs/a.json", site_dir=tmp_path)


def test_pipeline_start_skip_if_running(tmp_path: Path):
    from contextlib import contextmanager
    from evileye.stack_control import SpawnResult

    @contextmanager
    def noop_lock(_site):
        yield

    guard = EnsureResult(
        skipped=True,
        existing_pid=77,
        existing_mode="managed",
        config_path="configs/a.json",
    )
    with patch("evileye.stack_control._resolve_site", return_value=tmp_path), patch(
        "evileye.site_runtime_guard.spawn_lock", noop_lock
    ), patch("evileye.site_runtime_guard.ensure_pipeline_singleton", return_value=guard), patch(
        "evileye.stack_control.spawn_managed_pipeline"
    ) as spawn:
        result = pipeline_start("configs/a.json", site_dir=tmp_path, skip_if_running=True)
    spawn.assert_not_called()
    assert result.pid == 77
    assert result.mode == "managed"


def test_reload_web_with_pipeline_uses_replace(tmp_path: Path):
    from evileye.stack_control import ReloadResult, SpawnResult, StackState

    state = StackState(site_dir=tmp_path, in_container=False)
    with patch("evileye.stack_control.discover_stack_state", return_value=state), patch(
        "evileye.stack_control.stop_pipelines"
    ), patch("evileye.stack_control.restart_web_layer"), patch(
        "evileye.stack_control.wait_web_ready", return_value=True
    ), patch("evileye.stack_control.pipeline_start") as start, patch(
        "evileye.stack_control.resolve_production_config", return_value="configs/a.json"
    ):
        start.return_value = SpawnResult(pid=1, mode="managed", config_path="configs/a.json")
        reload_web(site_dir=tmp_path, with_pipeline=True, config="configs/a.json")
    start.assert_called_once()
    assert start.call_args.kwargs.get("replace") is True


def test_singleton_warnings_duplicate_pipeline(tmp_path: Path):
    from types import SimpleNamespace

    snap_runs = [
        {"pid": 1, "config_path": "configs/a.json", "alive": True},
        {"pid": 2, "config_path": "configs/a.json", "alive": True},
    ]
    with patch("evileye.site_runtime_guard.discover_site_runs") as discover, patch(
        "evileye.core.process_control.pid_exists", return_value=True
    ), patch("evileye.service_manager.is_web_os_service_active", return_value=False):
        discover.return_value = SimpleNamespace(
            pipeline_runs=snap_runs,
            web_foreground_pids=[],
        )
        warnings = singleton_warnings(tmp_path)
    assert any("duplicate_pipeline_detected" in w for w in warnings)


def test_spawn_lock_uses_monitor_dir(tmp_path: Path):
    (tmp_path / "monitor").mkdir()
    with patch("evileye.site_runtime_guard.with_file_lock") as lock:
        lock.return_value.__enter__ = lambda *_a, **_k: None
        lock.return_value.__exit__ = lambda *_a, **_k: None
        with spawn_lock(tmp_path):
            pass
        lock.assert_called_once()
        assert lock.call_args.args[0] == tmp_path / "monitor" / ".spawn.lock"


def test_ensure_web_singleton_allows_service_main_process(tmp_path: Path):
    from types import SimpleNamespace

    from evileye.site_runtime_guard import ensure_web_singleton

    snap = SimpleNamespace(
        web_foreground_pids=[12345],
        web_listener_pid=None,
    )
    with patch("evileye.site_runtime_guard.discover_site_runs", return_value=snap), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=True
    ), patch("evileye.service_manager.web_service_main_pid", return_value=12345), patch(
        "evileye.site_runtime_guard._service_process_tree_pids", return_value={12345}
    ), patch("evileye.service_manager.probe_port_scheme", return_value="closed"), patch(
        "evileye.site_profile.service_port", return_value=8181
    ):
        result = ensure_web_singleton(tmp_path, self_pid=12345)
    assert result.ok is True


def test_ensure_web_singleton_blocks_manual_start_when_service_active(tmp_path: Path):
    from types import SimpleNamespace

    from evileye.site_runtime_guard import DuplicateWebError, ensure_web_singleton

    snap = SimpleNamespace(web_foreground_pids=[], web_listener_pid=None)
    with patch("evileye.site_runtime_guard.discover_site_runs", return_value=snap), patch(
        "evileye.service_manager.is_web_os_service_active", return_value=True
    ), patch("evileye.service_manager.web_service_main_pid", return_value=99999), patch(
        "evileye.site_runtime_guard._service_process_tree_pids", return_value={99999}
    ), patch("evileye.service_manager.probe_port_scheme", return_value="closed"), patch(
        "evileye.site_profile.service_port", return_value=8181
    ):
        with pytest.raises(DuplicateWebError, match="os_service_active"):
            ensure_web_singleton(tmp_path, self_pid=12345)


def test_find_alive_pipelines_filters_by_site(tmp_path: Path):
    from types import SimpleNamespace

    with patch("evileye.site_runtime_guard.discover_site_runs") as discover, patch(
        "evileye.watchdog_native.find_cli_and_child", return_value=(None, None)
    ), patch("evileye.site_runtime_guard.pid_exists", return_value=True):
        discover.return_value = SimpleNamespace(
            pipeline_runs=[
                {"pid": 10, "config_path": str(tmp_path / "configs/a.json"), "managed": True}
            ]
        )
        matches = find_alive_pipelines_for_config(tmp_path, "a.json")
    assert len(matches) == 1
    assert matches[0]["pid"] == 10
