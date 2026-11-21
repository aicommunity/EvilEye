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
