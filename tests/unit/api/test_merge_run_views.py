"""Runtime registry wins over stale ConfigRunManager rows when the process is alive."""

from evileye.api.core.runtime_registry import merge_run_views


def test_merge_prefers_registry_when_alive():
    runtime = {
        "id": 29,
        "state": "running",
        "pid": 358441,
        "alive": True,
        "config_path": "/site/configs/poly.json",
    }
    manager = {
        "id": 29,
        "state": "created",
        "pid": None,
        "name": "ConfigRun-29",
        "config_path": "/site/configs/poly.json",
    }
    merged = merge_run_views(runtime, manager)
    assert merged is not None
    assert merged["state"] == "running"
    assert merged["pid"] == 358441
    assert merged["alive"] is True
    assert merged["name"] == "ConfigRun-29"


def test_merge_keeps_manager_starting_when_registry_not_alive():
    runtime = {"id": 3, "state": "stopped", "pid": None, "alive": False}
    manager = {"id": 3, "state": "starting", "pid": 99}
    merged = merge_run_views(runtime, manager)
    assert merged is not None
    assert merged["state"] == "starting"
    assert merged["pid"] == 99


def test_merge_manager_only():
    manager = {"id": 1, "state": "created", "pid": None}
    assert merge_run_views(None, manager) == manager


def test_merge_runtime_only():
    runtime = {"id": 2, "state": "running", "alive": True, "pid": 1}
    assert merge_run_views(runtime, None) == runtime
