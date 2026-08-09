from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

from evileye.core import process_control


def test_terminate_tree_windows_uses_psutil(monkeypatch):
    monkeypatch.setattr(process_control.sys, "platform", "win32")
    parent = MagicMock()
    child = MagicMock()
    parent.children.return_value = [child]
    with patch.object(process_control, "psutil") as ps:
        ps.Process.return_value = parent
        ps.Error = Exception
        ps.wait_procs.return_value = ([], [])
        process_control.terminate_tree(123, grace_sec=0.01)
        parent.terminate.assert_called()
        child.terminate.assert_called()


def test_find_pids_by_cmdline_regex():
    with patch.object(process_control, "psutil") as ps:
        proc = MagicMock()
        proc.info = {"pid": 7, "cmdline": ["python", "process.py", "--config", "foo.json"]}
        ps.process_iter.return_value = [proc]
        ps.Error = Exception
        found = process_control.find_pids_by_cmdline_regex([r"process\.py.*foo"])
        assert found == [7]


def test_is_zombie_via_psutil():
    with patch.object(process_control, "psutil") as ps:
        proc = MagicMock()
        proc.status.return_value = ps.STATUS_ZOMBIE
        ps.Process.return_value = proc
        ps.Error = Exception
        assert process_control.is_zombie(42) is True


def test_is_zombie_false_for_running():
    with patch.object(process_control, "psutil") as ps:
        proc = MagicMock()
        proc.status.return_value = "running"
        ps.STATUS_ZOMBIE = "zombie"
        ps.Process.return_value = proc
        ps.Error = Exception
        assert process_control.is_zombie(42) is False


def test_terminate_tree_returns_immediately_for_zombie_only_group(monkeypatch):
    """Zombie leader must not block for the full grace period (Ctrl+C hang fix)."""
    monkeypatch.setattr(process_control.sys, "platform", "linux")
    grace = 2.0
    with (
        patch.object(process_control.os, "getpgid", return_value=1001),
        patch.object(process_control.os, "killpg") as killpg,
        patch.object(process_control, "_process_group_has_live_members", return_value=False),
    ):
        started = time.monotonic()
        process_control.terminate_tree(1001, grace_sec=grace)
        elapsed = time.monotonic() - started

    killpg.assert_called_once_with(1001, process_control.signal.SIGTERM)
    assert elapsed < 0.5, f"terminate_tree blocked for {elapsed:.2f}s on zombie-only group"


def test_terminate_tree_sigkills_when_live_members_remain(monkeypatch):
    monkeypatch.setattr(process_control.sys, "platform", "linux")
    grace = 0.25
    with (
        patch.object(process_control.os, "getpgid", return_value=2002),
        patch.object(process_control.os, "killpg") as killpg,
        patch.object(process_control, "_process_group_has_live_members", return_value=True),
    ):
        started = time.monotonic()
        process_control.terminate_tree(2002, grace_sec=grace)
        elapsed = time.monotonic() - started

    assert killpg.call_count >= 2
    assert killpg.call_args_list[0].args == (2002, process_control.signal.SIGTERM)
    assert killpg.call_args_list[-1].args == (2002, process_control.signal.SIGKILL)
    assert elapsed >= grace


def test_process_group_has_live_members_skips_zombies(monkeypatch):
    zombie = MagicMock()
    zombie.info = {"pid": 10}
    live = MagicMock()
    live.info = {"pid": 11}

    def getpgid(pid):
        return 55 if pid in (10, 11) else -1

    with (
        patch.object(process_control, "psutil") as ps,
        patch.object(process_control.os, "getpgid", side_effect=getpgid),
        patch.object(process_control, "is_zombie", side_effect=lambda pid: pid == 10),
    ):
        ps.process_iter.return_value = [zombie, live]
        ps.Error = Exception
        assert process_control._process_group_has_live_members(55) is True

    with (
        patch.object(process_control, "psutil") as ps,
        patch.object(process_control.os, "getpgid", side_effect=getpgid),
        patch.object(process_control, "is_zombie", return_value=True),
    ):
        ps.process_iter.return_value = [zombie]
        ps.Error = Exception
        assert process_control._process_group_has_live_members(55) is False
