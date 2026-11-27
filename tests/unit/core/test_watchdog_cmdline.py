"""Watchdog must match a config argv element, not a similar substring."""

from evileye.watchdog_native import cmdline_matches_target


def test_short_config_does_not_match_longer_name():
    argv = ["evileye", "run", "configs/cam-2.json"]
    assert cmdline_matches_target(argv, "cam.json", kind="cli") is False
    assert cmdline_matches_target(["evileye", "run", "configs/cam.json"], "cam.json", kind="cli") is True


def test_child_process_matches_config_argument():
    argv = ["python", "evileye/process.py", "configs/cam.json"]
    assert cmdline_matches_target(argv, "configs/cam.json", kind="child") is True
    assert cmdline_matches_target(["python", "evileye/process.py", "/cam/other.json"], "cam.json", kind="child") is False


class TestPidRecord:
    def test_record_roundtrip_and_preferrence(self, tmp_path, monkeypatch):
        import os

        from evileye import watchdog_native as wd

        config = str(tmp_path / "system.json")
        cli = os.getpid()
        wd.write_pid_record(config, cli_pid=cli, child_pid=0, root=tmp_path)
        assert wd.read_pid_record(config, root=tmp_path) == {"cli": cli}
        # find_cli_and_child prefers the record over the argv scan.
        found_cli, _child = wd.find_cli_and_child(config, root=tmp_path)
        assert found_cli == cli

    def test_stale_record_is_ignored(self, tmp_path):
        from evileye import watchdog_native as wd

        config = str(tmp_path / "system.json")
        # PID 0x7fffffff does not exist; the record must be unusable.
        wd.write_pid_record(config, cli_pid=2_147_000_000, child_pid=2_147_000_001, root=tmp_path)
        assert wd.read_pid_record(config, root=tmp_path) == {}

    def test_write_merges_existing_fields(self, tmp_path):
        import os

        from evileye import watchdog_native as wd

        config = str(tmp_path / "system.json")
        # Both PIDs must be alive for read_pid_record to report them.
        cli_pid, child_pid = os.getppid(), os.getpid()
        wd.write_pid_record(config, cli_pid=cli_pid, root=tmp_path)
        wd.write_pid_record(config, child_pid=child_pid, root=tmp_path)
        record = wd.read_pid_record(config, root=tmp_path)
        assert record.get("cli") == cli_pid
        assert record.get("child") == child_pid

    def test_clear_record(self, tmp_path):
        import os

        from evileye import watchdog_native as wd

        config = str(tmp_path / "system.json")
        wd.write_pid_record(config, cli_pid=os.getpid(), root=tmp_path)
        wd.clear_pid_record(config, root=tmp_path)
        assert wd.read_pid_record(config, root=tmp_path) == {}
