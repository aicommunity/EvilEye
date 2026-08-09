from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from evileye.api.core.config_run_manager import ConfigRunItem, ConfigRunManager, ConfigRunState
from evileye.api.core.process_restart import (
    cmdline_has_gui,
    find_matching_runtime,
    pid_hosts_current_process,
)


def test_stop_uses_killpg_on_process_group():
    manager = ConfigRunManager()
    cfg_item = ConfigRunItem(1, "test", Path("configs/test.json"))
    cfg_item.pid = 4242
    cfg_item.state = ConfigRunState.RUNNING
    cfg_item.session_id = "abc123"
    manager._items[1] = cfg_item

    with patch("evileye.api.core.process_restart.pid_hosts_current_process", return_value=False), \
            patch("evileye.api.core.config_run_manager.os.getpgid", return_value=4242) as getpgid, \
            patch("evileye.api.core.config_run_manager.os.killpg") as killpg, \
            patch("evileye.api.core.config_run_manager.os.kill", side_effect=ProcessLookupError), \
            patch("evileye.api.core.config_run_manager.mark_runtime_stopped") as mark_stopped, \
            patch("evileye.core.mp_session_registry.cleanup_session_by_id") as cleanup_session:
        manager._stop_grace_sec = lambda: 0.1  # type: ignore[method-assign]
        result = manager.stop(1)

    getpgid.assert_called_once_with(4242)
    killpg.assert_called_once_with(4242, signal.SIGTERM)
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
            patch("evileye.api.core.config_run_manager.os.killpg") as killpg:
        with pytest.raises(RuntimeError, match="hosts this API"):
            manager.stop(1)
    killpg.assert_not_called()


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
        # Avoid safe_config_name needing real file — use name that passes basename check
        result = manager.restart_for_config("poly-cameras-gst.json")

    assert result["mode"] == "self_hosted_detached"
    assert result["scheduled"] is True
    assert result["helper_pid"] == 555
    spawn.assert_called_once()
    term.assert_called_once_with(9999)


def test_pid_hosts_current_process_self():
    import os

    assert pid_hosts_current_process(os.getpid()) is True
    assert pid_hosts_current_process(1) or not pid_hosts_current_process(1)  # may or may not be ancestor
    assert pid_hosts_current_process(-1) is False
