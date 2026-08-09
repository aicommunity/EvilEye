from __future__ import annotations

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
