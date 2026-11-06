"""Runtime ownership checks must work without Linux /proc, including Windows."""

from types import SimpleNamespace

import pytest

from evileye.api.core import runtime_registry as registry


@pytest.mark.parametrize("command,expected", [
    (["python", "/opt/app/evileye/process.py", "--config", "{config}"], True),
    (["python.exe", r"C:\app\evileye\process.py", "--config", "{config}"], True),
    (["python", "-m", "evileye.process", "--config={config}"], True),
    (["python", "evileye/process.py", "--video", "movie.mp4"], True),
    (["python", "/opt/unrelated/process.py", "--config", "{config}"], False),
    (["python", "/opt/app/evileye/process.py", "--help"], False),
])
def test_pipeline_owner_liveness_from_portable_commandline(tmp_path, monkeypatch, command, expected):
    config = str(tmp_path / "sample.json")
    command = [part.replace("{config}", config) for part in command]

    class Process:
        def cmdline(self):
            return command

        def environ(self):
            return {"EVILEYE_PIPELINE_ID": "314", "EVILEYE_MANAGED_RUN": "1"}

        def is_running(self):
            return True

        def status(self):
            return registry.psutil.STATUS_RUNNING

    monkeypatch.setattr(registry.psutil, "Process", lambda _pid: Process())
    assert registry._is_pid_alive(123) is expected
    if expected:
        info = registry._parse_process_cmdline(123)
        assert info["pipeline_id"] == "314"
        assert info["managed"] is True


def test_discovery_uses_portable_process_inventory(tmp_path, monkeypatch):
    monkeypatch.setattr(registry, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(registry, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(registry, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(registry, "LOCK_FILE", tmp_path / ".lock")
    monkeypatch.setattr(registry.psutil, "process_iter", lambda _attrs: [SimpleNamespace(info={"pid": 123})])
    monkeypatch.setattr(registry, "_parse_process_cmdline", lambda _pid: {
        "config_path": str(tmp_path / "sample.json"), "pipeline_id": "314", "managed": True,
    })
    monkeypatch.setattr(registry, "_is_pid_alive", lambda _pid: True)

    registry.discover_process_runtimes()

    record = registry.load_runtime_record(314)
    assert record["state"] == "running"
    assert record["pid"] == 123
    assert record["config_path"] == str((tmp_path / "sample.json").resolve())
