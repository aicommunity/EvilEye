from __future__ import annotations

import signal
from pathlib import Path
from unittest.mock import patch

from evileye.api.core.config_run_manager import ConfigRunItem, ConfigRunManager, ConfigRunState


def test_stop_uses_killpg_on_process_group():
    manager = ConfigRunManager()
    cfg_item = ConfigRunItem(1, "test", Path("configs/test.json"))
    cfg_item.pid = 4242
    cfg_item.state = ConfigRunState.RUNNING
    cfg_item.session_id = "abc123"
    manager._items[1] = cfg_item

    with patch("evileye.api.core.config_run_manager.os.getpgid", return_value=4242) as getpgid, \
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
