import json
from pathlib import Path

from typer.testing import CliRunner

from evileye.cli import app
from evileye.core.pipeline_topology import PipelineNode, PipelineTopology

runner = CliRunner()


def test_inspect_json_does_not_include_config_values(tmp_path: Path, monkeypatch):
    import evileye.cli_commands.pipeline_inspect as command

    config_path = tmp_path / "pipeline.json"
    config_path.write_text(json.dumps({"pipeline": {"pipeline_class": "PipelineSurveillance", "sources": [
        {"camera": "rtsp://operator:very-secret@camera.local/stream", "source_ids": [0]},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(command, "register_builtins", lambda: None)
    monkeypatch.setattr(command, "build_topology", lambda _config: PipelineTopology(
        "PipelineSurveillance", "PipelineSurveillance",
        (PipelineNode("sources:0:VideoCaptureOpencv", "Cam1", "source", "Sources", "VideoCaptureOpencv"),),
        (),
    ))

    result = runner.invoke(app, ["pipeline", "inspect", str(config_path), "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["view"] == "configuration"
    assert payload["nodes"][0]["status"] == "configured"
    assert "very-secret" not in result.output
    assert "operator" not in result.output
    assert "camera.local" not in result.output


def test_configure_without_tty_exits_without_creating_a_config(tmp_path: Path):
    path = tmp_path / "new.json"
    result = runner.invoke(app, ["pipeline", "configure", str(path)])
    assert result.exit_code == 2
    assert "interactive TTY" in result.output
    assert not path.exists()


def test_inspection_prefers_refreshed_run_state_over_last_snapshot(monkeypatch):
    import time
    import evileye.cli_commands.pipeline_inspect as command

    topology = PipelineTopology(
        "sample", "Sample",
        (PipelineNode("detectors:0:Rule", "Rule", "detector", "Detectors", "Rule"),),
        (),
    )
    monkeypatch.setattr(command, "build_topology", lambda _config: topology)
    snapshot = {
        "state": "running",
        "runtime_telemetry": {
            "published_at": time.time(),
            "module_instances": {"detectors:0:Rule": {"worker_running": True}},
        },
    }

    result = command._runtime_topology({}, snapshot, {"state": "stopped"})

    assert result.nodes[0].status == "stale"


def test_runtime_watch_stops_cleanly_when_run_stops(monkeypatch):
    import evileye.cli_commands.pipeline_inspect as command

    class FakeLive:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def update(self, _renderable):
            pass

    class FakeConsole:
        is_terminal = True

        def print(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(command, "console", FakeConsole())
    monkeypatch.setattr(command, "register_builtins", lambda: None)
    monkeypatch.setattr("rich.live.Live", FakeLive)
    monkeypatch.setattr(command.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(command, "_runtime_topology", lambda *_args: PipelineTopology(
        "sample", "Sample", (), (),
    ))
    results = iter([
        ({}, {"state": "running", "config_path": "site.json"}, {}),
        ({}, {"state": "stopped", "config_path": "site.json"}, {}),
    ])
    monkeypatch.setattr(command, "_load_run", lambda _run_id: next(results))

    command.inspect_pipeline(None, 42, "tree", True)


def test_runtime_watch_reports_missing_snapshot_without_traceback(monkeypatch):
    import evileye.cli_commands.pipeline_inspect as command

    class FakeLive:
        def __init__(self, *_args, **_kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def update(self, _renderable):
            pass

    class FakeConsole:
        is_terminal = True

        def print(self, *_args, **_kwargs):
            pass

    monkeypatch.setattr(command, "console", FakeConsole())
    monkeypatch.setattr(command, "register_builtins", lambda: None)
    monkeypatch.setattr("rich.live.Live", FakeLive)
    monkeypatch.setattr(command.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(command, "_runtime_topology", lambda *_args: PipelineTopology(
        "sample", "Sample", (), (),
    ))
    calls = 0

    def load_run(_run_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            return {}, {"state": "running", "config_path": "site.json"}, {}
        raise FileNotFoundError("runtime snapshot disappeared")

    monkeypatch.setattr(command, "_load_run", load_run)

    command.inspect_pipeline(None, 42, "tree", True)


def test_plugin_list_can_filter_registered_sources():
    result = runner.invoke(app, ["plugin", "list", "--kind", "source"])

    assert result.exit_code == 0, result.output
    assert "evileye/VideoCaptureOpencv" in result.output
    assert "evileye/VideoCaptureGStreamer" in result.output
    assert "ObjectDetectorYolo" not in result.output


def test_inspect_reads_real_saved_run_snapshot_with_qualified_module_health(tmp_path, monkeypatch):
    import os
    import time
    from evileye.api.core import runtime_registry as registry

    monkeypatch.setattr(registry, "RUNTIME_ROOT", tmp_path)
    monkeypatch.setattr(registry, "REGISTRY_DIR", tmp_path / "pipelines")
    monkeypatch.setattr(registry, "SNAPSHOT_DIR", tmp_path / "snapshots")
    monkeypatch.setattr(registry, "LOCK_FILE", tmp_path / ".lock")
    # The test host is not an analytics owner; only its command identity is
    # substituted. Record/snapshot writes, process liveness, and CLI reads are real.
    monkeypatch.setattr(registry, "_parse_process_cmdline", lambda _pid: {"config_path": "sample.json"})
    registry.register_runtime(rid=842, pid=os.getpid(), config_path="sample.json", name="audit", source="test", frame_dir=None)
    registry.update_runtime_snapshot(842, state="running", config={
        "pipeline": {"detectors": [{"type": "ObjectDetectorYolo"}, {"type": "ObjectDetectorYolo"}]},
        "events_detectors": {"enabled": []},
    }, runtime_telemetry={
        "published_at": time.time(),
        "module_instances": {
            "detectors:0:evileye/ObjectDetectorYolo": {"worker_running": True},
            "detectors:1:evileye/ObjectDetectorYolo": {"worker_running": True, "degraded": True},
        },
    })

    result = runner.invoke(app, ["pipeline", "inspect", "--run", "842", "--format", "json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["view"] == "runtime" and payload["run_id"] == 842
    assert payload["telemetry"]["status"] == "fresh"
    assert [node["status"] for node in payload["nodes"]] == ["running", "degraded"]


def test_plugin_list_does_not_advertise_callable_validator_as_an_editable_form(monkeypatch):
    import uuid
    from evileye.core.plugins import PluginSpec, ModuleSpec, PLUGIN_API_VERSION, plugin_registry
    import evileye.core.builtin_inventory as inventory

    plugin_id = "test.validator." + uuid.uuid4().hex
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(
        ModuleSpec("rule", "alarm_detector", dict, config_schema=lambda data: data),
    )))
    monkeypatch.setattr(inventory, "register_builtins", lambda: None)
    result = runner.invoke(app, ["plugin", "list", "--kind", "alarm_detector"])
    assert result.exit_code == 0, result.output
    assert plugin_id + "/rule" in result.output
    assert "form_schema=no" in result.output
