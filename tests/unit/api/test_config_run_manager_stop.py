from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evileye.api.core.config_run_manager import ConfigRunItem, ConfigRunManager, ConfigRunState
from evileye.api.core.process_restart import (
    cmdline_has_gui,
    find_matching_runtime,
    pid_hosts_current_process,
)


def test_stop_uses_terminate_tree():
    manager = ConfigRunManager()
    cfg_item = ConfigRunItem(1, "test", Path("configs/test.json"))
    cfg_item.pid = 4242
    cfg_item.state = ConfigRunState.RUNNING
    cfg_item.session_id = "abc123"
    manager._items[1] = cfg_item

    with patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=False), \
            patch("evileye.core.process_control.terminate_tree") as terminate_tree, \
            patch("evileye.core.process_control.pid_exists", return_value=False), \
            patch("evileye.api.core.config_run_manager.mark_runtime_stopped") as mark_stopped, \
            patch("evileye.core.mp_session_registry.cleanup_session_by_id") as cleanup_session:
        manager._stop_grace_sec = lambda: 0.1  # type: ignore[method-assign]
        result = manager.stop(1)

    terminate_tree.assert_called_once()
    assert terminate_tree.call_args[0][0] == 4242
    cleanup_session.assert_called_once_with("abc123")
    mark_stopped.assert_called_once()
    assert result["state"] == ConfigRunState.STOPPED


def test_stop_refuses_to_kill_api_host_process():
    manager = ConfigRunManager()
    cfg_item = ConfigRunItem(1, "test", Path("configs/test.json"))
    cfg_item.pid = 111
    cfg_item.state = ConfigRunState.RUNNING
    manager._items[1] = cfg_item

    with patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=True), \
            patch("evileye.core.process_control.terminate_tree") as terminate_tree:
        with pytest.raises(RuntimeError, match="hosts this API"):
            manager.stop(1)
    terminate_tree.assert_not_called()


def test_cmdline_has_gui():
    assert cmdline_has_gui(["python", "process.py", "--config", "a.json", "--gui"]) is True
    assert cmdline_has_gui(["python", "process.py", "--config", "a.json", "--no-gui"]) is False
    assert cmdline_has_gui(["python", "process.py", "--config", "a.json"]) is True


def test_find_matching_runtime_prefers_managed():
    records = {
        1: {
            "id": 1,
            "config_path": "/x/configs/poly-cameras-gst.json",
            "state": "running",
            "alive": True,
            "managed": False,
            "source": "process",
        },
        2: {
            "id": 2,
            "config_path": "/x/configs/poly-cameras-gst.json",
            "state": "running",
            "alive": True,
            "managed": True,
            "source": "web",
        },
    }
    match = find_matching_runtime(records, "poly-cameras-gst.json")
    assert match is not None
    assert match["id"] == 2


def test_restart_self_hosted_spawns_helper_and_terms_pid():
    manager = ConfigRunManager()
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={
        9: {
            "id": 9,
            "pid": 9999,
            "config_path": str(Path("configs/poly-cameras-gst.json").resolve()),
            "state": "running",
            "alive": True,
            "managed": False,
            "source": "process",
        }
    }), patch.object(manager, "list", return_value={}), \
            patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=True), \
            patch("evileye.api.core.process_restart.read_cmdline", return_value=[
                "python", "process.py", "--config", "configs/poly-cameras-gst.json", "--gui", "--no-autoclose"
            ]), \
            patch("evileye.api.core.process_restart.spawn_detached_restart_helper", return_value=555) as spawn, \
            patch("evileye.api.core.process_restart.signal_pid_term") as term:
        result = manager.restart_for_config("poly-cameras-gst.json")

    assert result["mode"] == "self_hosted_detached"
    assert result["scheduled"] is True
    assert result["helper_pid"] == 555
    spawn.assert_called_once()
    term.assert_called_once_with(9999)


def test_restart_managed_site_uses_stack_control():
    manager = ConfigRunManager()
    spawn = MagicMock()
    spawn.pid = 4242
    spawn.mode = "managed"
    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={
        24: {
            "id": 24,
            "pid": 2083042,
            "config_path": "/home/user/EvilEyeDeploy/configs/poly-cameras-gst.json",
            "state": "running",
            "alive": True,
            "managed": True,
            "source": "web",
        }
    }), patch.object(manager, "list", return_value={}), \
            patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=False), \
            patch("evileye.stack_control.should_use_managed_launch", return_value=True), \
            patch("evileye.stack_control.pipeline_restart", return_value=spawn) as restart:
        result = manager.restart_for_config("poly-cameras-gst.json")

    restart.assert_called_once()
    assert restart.call_args.kwargs.get("hold") is False
    assert result["mode"] == "managed_restart"
    assert result["pid"] == 4242
    assert result["previous_rid"] == 24
    assert manager._items == {}


def test_restart_direct_site_raises_when_start_fails(tmp_path: Path):
    manager = ConfigRunManager()
    cfg = tmp_path / "configs"
    cfg.mkdir(parents=True)
    (cfg / "test.json").write_text("{}", encoding="utf-8")

    with patch("evileye.api.core.runtime_registry.list_runtime_records", return_value={
        1: {
            "id": 1,
            "pid": 100,
            "config_path": str(cfg / "test.json"),
            "state": "running",
            "alive": True,
            "managed": False,
            "source": "process",
        }
    }), patch.object(manager, "list", return_value={}), \
            patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=False), \
            patch("evileye.stack_control.should_use_managed_launch", return_value=False), \
            patch("evileye.stack_control.stop_pipelines"), \
            patch.object(manager, "_wait_config_pipeline_stopped"), \
            patch.object(manager, "next_run_id", return_value=2), \
            patch.object(manager, "create", return_value={"id": 2}), \
            patch.object(
                manager,
                "start",
                return_value={"id": 2, "state": ConfigRunState.ERROR, "error": "blocked"},
            ):
        with pytest.raises(RuntimeError, match="blocked"):
            manager.restart_for_config("test.json")


def test_pid_hosts_current_process_self():
    import os

    assert pid_hosts_current_process(os.getpid()) is True
    assert pid_hosts_current_process(1) or not pid_hosts_current_process(1)
    assert pid_hosts_current_process(-1) is False
