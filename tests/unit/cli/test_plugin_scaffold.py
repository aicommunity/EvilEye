from __future__ import annotations

import importlib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from evileye.cli import app
from evileye.cli_commands.plugin_scaffold import (
    PluginScaffoldError,
    create_plugin_project,
    template_names,
)
from evileye.core.plugins import PluginRegistry

runner = CliRunner()


@pytest.mark.parametrize("template", template_names())
def test_generated_plugin_templates_import_and_register(
    tmp_path: Path, monkeypatch, template: str
):
    project_dir = create_plugin_project(f"sample-{template}", tmp_path, template)
    package_name = f"sample_{template}"
    monkeypatch.syspath_prepend(str(project_dir))

    plugin_module = importlib.import_module(f"{package_name}.plugin")
    manifest = plugin_module.load_plugin()
    registry = PluginRegistry()
    registry.register_plugin(manifest)

    assert manifest.plugin_id == package_name
    assert len(manifest.modules) + len(manifest.pipelines) == 1
    assert (project_dir / "pyproject.toml").is_file()
    assert (project_dir / "README.md").is_file()

    if template == "processor":
        processor = manifest.modules[0].factory({"label": "test"})
        state = processor.create_state({})
        assert processor.process_item({"value": 1}, state)["plugin_label"] == "test"

    elif template == "detector":
        from evileye.core.frame import Frame
        from evileye.object_detector import DetectionResultList

        detector = manifest.modules[0].factory({})
        frame = Frame()
        frame.source_id = 2
        frame.frame_id = 9
        frame.time_stamp = 1.0
        state = detector.create_state({})
        detections, returned_frame = detector.process_item([{}, frame], state)
        assert isinstance(detections, DetectionResultList)
        assert detections.source_id == 2
        assert returned_frame is frame

    elif template == "alarm":
        from evileye.core.contracts import EventUpdate
        from evileye.events_detectors.alarm_event import AlarmEvent

        rule = manifest.modules[0].factory({"required_attributes": ["helmet"]})
        state = rule.create_state({})
        update = EventUpdate(
            sequence=1,
            kind="object_snapshot",
            source_id=0,
            payload={
                "active": [{
                    "object_id": "person-7",
                    "attributes": {},
                }]
            },
        )
        alarms = rule.process_update(update, state)
        assert len(alarms) == 1
        assert isinstance(alarms[0], AlarmEvent)
        assert alarms[0].alarm_type == "ppe_violation"

    elif template == "source":
        from evileye.core.frame import Frame

        source = manifest.modules[0].factory(
            {"source_id": 3, "width": 8, "height": 6, "max_frames": 1}
        )
        source.open()
        frame = source.read()
        assert isinstance(frame, Frame)
        assert frame.source_id == 3
        assert frame.image.shape == (6, 8, 3)
        assert source.read() is None
        source.close()

    elif template == "pipeline":
        from evileye.core.contracts import PipelineConfig, PipelineDependencies

        pipeline = manifest.pipelines[0].factory(
            PipelineDependencies(config=PipelineConfig(raw_config={"marker": "test"}))
        )
        pipeline.start()
        assert pipeline.process() == {"marker": "test", "sequence": 1}
        pipeline.stop()


def test_create_command_writes_package_in_requested_directory(tmp_path: Path):
    result = runner.invoke(
        app,
        [
            "plugin",
            "create",
            "site-safety",
            "--template",
            "alarm",
            "--output-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == 0, result.output
    plugin_dir = tmp_path / "site-safety"
    assert (plugin_dir / "pyproject.toml").is_file()
    assert (plugin_dir / "site_safety" / "plugin.py").is_file()
    assert "site_safety/example_alarm" in result.output
    assert "pip install -e" in result.output
    assert "pip install --upgrade pip setuptools" in result.output


def test_template_list_shows_available_starters():
    result = runner.invoke(app, ["plugin", "templates"])

    assert result.exit_code == 0, result.output
    for name in ("processor", "detector", "alarm", "source", "pipeline"):
        assert name in result.output


def test_create_refuses_existing_destination_without_overwriting(tmp_path: Path):
    destination = tmp_path / "my-plugin"
    destination.mkdir()
    sentinel = destination / "keep.txt"
    sentinel.write_text("user data", encoding="utf-8")

    with pytest.raises(PluginScaffoldError, match="already exists"):
        create_plugin_project("my-plugin", tmp_path, "processor")

    assert sentinel.read_text(encoding="utf-8") == "user data"


@pytest.mark.parametrize("name", ("../outside", "9plugin", "my--plugin", "class", "evileye"))
def test_create_rejects_unsafe_or_reserved_names(tmp_path: Path, name: str):
    with pytest.raises(PluginScaffoldError):
        create_plugin_project(name, tmp_path, "processor")
