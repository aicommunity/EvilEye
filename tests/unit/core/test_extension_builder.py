from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from evileye.core.extension_builder import (
    create_plugin_archive,
    create_plugin_operation,
    extension_catalog,
    get_plugin_operation,
    list_plugin_operations,
    preview_pipeline,
    save_pipeline,
)
from evileye.core.pipeline_configuration import mask_config_secrets, merge_preserving_secrets
from evileye.core.plugin_scaffold import PluginScaffoldError, create_plugin_project


def test_catalog_exposes_builtin_pipelines_and_module_schemas():
    catalog = extension_catalog()
    pipeline_ids = {item["config_id"] for item in catalog["pipelines"]}
    assert {"PipelineSurveillance", "PipelineDeclarative", "PipelineCapture"} <= pipeline_ids
    from evileye.core.builtin_module_schemas import BUILTIN_MODULE_SCHEMAS

    modules_by_id = {item["id"]: item for item in catalog["modules"]}
    builtin_ids = {f"evileye/{module_id}" for module_id in BUILTIN_MODULE_SCHEMAS}
    assert all(modules_by_id[module_id]["config_schema"] for module_id in builtin_ids)


def test_catalog_exposes_plugin_ui_schema_without_expanding_it(monkeypatch):
    from evileye.core import plugins
    from evileye.core.plugins import ModuleSpec, PluginRegistry, PluginSpec

    registry = PluginRegistry()
    monkeypatch.setattr(plugins, "plugin_registry", registry)
    from evileye.core.builtin_inventory import register_builtins

    register_builtins()
    registry.register_plugin(PluginSpec(
        "ui_hints",
        plugins.PLUGIN_API_VERSION,
        modules=(ModuleSpec(
            "sample",
            "processor_item",
            lambda: None,
            config_schema={"type": "object", "properties": {"mode": {"type": "string", "enum": ["a", "b"]}}},
            ui_schema={"mode": {"ui:widget": "radio", "ui:help": "Choose mode"}},
        ),),
    ))
    catalog = extension_catalog()
    item = next(module for module in catalog["modules"] if module["id"] == "ui_hints/sample")
    assert item["ui_schema"] == {"mode": {"ui:widget": "radio", "ui:help": "Choose mode"}}


def test_builtin_event_schemas_show_only_supported_settings_and_runtime_defaults():
    from evileye.core.builtin_module_schemas import BUILTIN_MODULE_SCHEMAS

    camera = BUILTIN_MODULE_SCHEMAS["CamEventsDetector"]["properties"]
    assert not {"event_threshold", "camera_cooldown_sec", "default_schedule"} & camera.keys()

    zone = BUILTIN_MODULE_SCHEMAS["ZoneEventsDetector"]["properties"]
    assert zone["sources"]["default"] == {}
    assert zone["event_threshold"]["default"] == 0
    assert zone["zone_left_threshold"]["default"] == 0
    assert "default_schedule" not in zone

    schedule = BUILTIN_MODULE_SCHEMAS["ScheduleAlarmEventsDetector"]["properties"]
    assert schedule["camera_cooldown_sec"]["default"] == 0
    assert schedule["default_schedule"]["properties"]["enabled"]["default"] is False
    assert schedule["default_schedule"]["properties"]["weekdays"]["default"] == list(range(7))
    assert schedule["default_schedule"]["properties"]["periods"]["default"] == []


def test_preview_is_metadata_only_and_reports_topology_without_opening_sources():
    config = {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [{"camera": "missing-video.mp4", "source_names": ["No connect"]}],
            "detectors": [],
        }
    }
    result = preview_pipeline(config)
    assert result["valid"] is True
    assert result["topology"]["nodes"][0]["stage"] == "Sources"
    assert result["topology"]["nodes"][0]["label"].startswith("No connect")


@pytest.mark.parametrize(
    ("config", "pipeline_id"),
    [
        ({"pipeline": {"pipeline_class": "PipelineDeclarative", "stages": [
            {"name": "capture", "kind": "source", "items": []},
            {"name": "detect", "kind": "step", "items": []},
        ]}}, "PipelineDeclarative"),
        ({"pipeline": {"pipeline_class": "PipelineCapture", "sources": []}}, "PipelineCapture"),
    ],
)
def test_preview_supports_other_builtin_pipeline_topologies(config, pipeline_id):
    preview = preview_pipeline(config)
    assert preview["valid"] is True
    assert preview["topology"]["pipeline_id"] == pipeline_id


def test_save_pipeline_preserves_unknown_fields_and_rotates_backups(tmp_path: Path):
    initial = {"pipeline": {"pipeline_class": "PipelineSurveillance", "sources": []}, "vendor": {"keep": 1}}
    created = save_pipeline("builder-test.json", initial, root=tmp_path, create_only=True)
    assert created["status"] == "created"
    for version in range(1, 14):
        changed = {**initial, "vendor": {"keep": version}}
        result = save_pipeline("builder-test.json", changed, root=tmp_path)
        assert result["status"] == "updated"
    path = tmp_path / "configs" / "builder-test.json"
    assert json.loads(path.read_text(encoding="utf-8"))["vendor"]["keep"] == 13
    backups = sorted((tmp_path / "configs").glob("builder-test.json.bak.*"))
    assert len(backups) == 10


def test_plugin_archive_contains_the_generated_project_and_refuses_overwrite(tmp_path: Path):
    project = create_plugin_project("archive-check", tmp_path, "alarm")
    archive = create_plugin_archive(project, tmp_path / "archive-check.zip")
    with zipfile.ZipFile(archive) as package:
        names = set(package.namelist())
    assert "archive-check/pyproject.toml" in names
    assert "archive-check/archive_check/plugin.py" in names
    with pytest.raises(PluginScaffoldError, match="already exists"):
        create_plugin_archive(project, archive)


def test_plugin_creation_persists_operation_and_archive_without_running_installer(tmp_path: Path, monkeypatch):
    from evileye.core import extension_builder

    monkeypatch.setattr(extension_builder, "dispatch_plugin_service_restart", lambda _op, _root: True)
    operation = create_plugin_operation("operation-sample", "alarm", root=tmp_path)
    stored = get_plugin_operation(operation["id"], root=tmp_path)
    assert stored["status"] == "queued"
    assert Path(stored["directory"]).is_dir()
    assert Path(stored["archive"]).is_file()
    assert stored["plugin_id"] == "operation_sample"


def test_plugin_operation_history_is_persisted_and_limited(tmp_path: Path):
    from evileye.core import extension_builder

    for index in range(3):
        extension_builder._store_operation({
            "id": f"0000000{index}-abcd",
            "status": "pending_restart",
            "name": f"plugin-{index}",
            "plugin_id": f"plugin_{index}",
            "updated_at": index + 1,
        }, tmp_path)

    recent = list_plugin_operations(limit=2, root=tmp_path)

    assert [item["name"] for item in recent] == ["plugin-2", "plugin-1"]


def _queued_plugin_operation(tmp_path: Path, monkeypatch, name: str = "worker-sample"):
    from evileye.core import extension_builder

    monkeypatch.setattr(extension_builder, "dispatch_plugin_service_restart", lambda _op, _root: True)
    return create_plugin_operation(name, "processor", root=tmp_path)


def test_plugin_worker_reports_missing_dependencies_without_installing(tmp_path: Path, monkeypatch):
    from evileye import service_manager
    from evileye.core import extension_builder

    operation = _queued_plugin_operation(tmp_path, monkeypatch, "missing-deps")
    monkeypatch.setattr(service_manager, "is_service_installed", lambda _root: False)
    monkeypatch.setattr(extension_builder, "_missing_dependencies", lambda _project: ["example-lib>=2"])
    monkeypatch.setattr(extension_builder.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("pip must not run"))

    extension_builder._install_and_restart(operation["id"], tmp_path)

    stored = get_plugin_operation(operation["id"], root=tmp_path)
    assert stored["status"] == "dependencies_missing"
    assert stored["missing_dependencies"] == ["example-lib>=2"]


def test_plugin_worker_reports_install_failure(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from evileye import service_manager
    from evileye.core import extension_builder

    operation = _queued_plugin_operation(tmp_path, monkeypatch, "install-failure")
    monkeypatch.setattr(service_manager, "is_service_installed", lambda _root: False)
    monkeypatch.setattr(extension_builder, "_missing_dependencies", lambda _project: [])
    monkeypatch.setattr(extension_builder.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1, stderr="pip failed", stdout=""))

    extension_builder._install_and_restart(operation["id"], tmp_path)

    stored = get_plugin_operation(operation["id"], root=tmp_path)
    assert stored["status"] == "failed"
    assert "pip failed" in stored["message"]


def test_plugin_worker_uses_no_deps_and_reports_pending_restart(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from evileye import service_manager
    from evileye.core import extension_builder

    operation = _queued_plugin_operation(tmp_path, monkeypatch, "pending-restart")
    captured = {}
    monkeypatch.setattr(service_manager, "is_service_installed", lambda _root: False)
    monkeypatch.setattr(extension_builder, "_missing_dependencies", lambda _project: [])
    monkeypatch.setattr(extension_builder, "_validate_installed_entry_point", lambda _plugin_id: None)
    monkeypatch.setattr(extension_builder.subprocess, "run", lambda args, **_kwargs: (captured.update(args=args) or SimpleNamespace(returncode=0, stderr="", stdout="")))

    extension_builder._install_and_restart(operation["id"], tmp_path)

    stored = get_plugin_operation(operation["id"], root=tmp_path)
    assert "--no-deps" in captured["args"]
    assert stored["status"] == "pending_restart"


def test_plugin_worker_restarts_matching_managed_service(tmp_path: Path, monkeypatch):
    from types import SimpleNamespace

    from evileye import service_manager, stack_control
    from evileye.core import extension_builder

    operation = _queued_plugin_operation(tmp_path, monkeypatch, "managed-restart")
    restart_calls = []
    monkeypatch.setattr(service_manager, "is_service_installed", lambda _root: True)
    monkeypatch.setattr(extension_builder, "_service_python_matches", lambda _root: True)
    monkeypatch.setattr(extension_builder, "_missing_dependencies", lambda _project: [])
    monkeypatch.setattr(extension_builder, "_validate_installed_entry_point", lambda _plugin_id: None)
    monkeypatch.setattr(extension_builder.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stderr="", stdout=""))
    monkeypatch.setattr(stack_control, "is_in_container", lambda: False)
    monkeypatch.setattr(extension_builder, "restart_plugin_service", lambda operation_id, root: restart_calls.append((operation_id, root)))

    extension_builder._install_and_restart(operation["id"], tmp_path)

    assert restart_calls == [(operation["id"], tmp_path)]
    assert get_plugin_operation(operation["id"], root=tmp_path)["status"] == "installed"


def test_plugin_operation_refuses_existing_directory(tmp_path: Path, monkeypatch):
    from evileye.core.extension_builder import plugin_root

    destination = plugin_root(tmp_path) / "collision"
    destination.mkdir()
    sentinel = destination / "user.txt"
    sentinel.write_text("keep", encoding="utf-8")
    with pytest.raises(PluginScaffoldError, match="already exists"):
        create_plugin_operation("collision", "processor", root=tmp_path)
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_plugin_operation_storage_rejects_redirected_metadata_path(tmp_path: Path, monkeypatch):
    from evileye.core.extension_builder import _operation_directory, plugin_root

    outside = tmp_path / "outside"
    outside.mkdir()
    metadata = plugin_root(tmp_path) / ".evileye"
    original_resolve = Path.resolve

    def resolve(path, *args, **kwargs):
        if path == metadata:
            return outside
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)

    with pytest.raises(PluginScaffoldError, match="may not point outside"):
        _operation_directory(tmp_path)
    assert list(outside.iterdir()) == []
    assert not (metadata / "operations").exists()


def test_config_secrets_are_masked_and_follow_named_items_when_reordered():
    existing = {
        "sources": [
            {"name": "camera-a", "source": "rtsp://alice:secret-a@camera/a", "api_token": "token-a"},
            {"name": "camera-b", "source": "rtsp://bob:secret-b@camera/b", "api_token": "token-b"},
        ]
    }
    masked = mask_config_secrets(existing)
    reordered = {
        "sources": [
            {"name": "camera-b", "source": "rtsp://***:***@camera/b", "api_token": "***"},
            {"name": "camera-a", "source": "rtsp://***:***@camera/a", "api_token": "***"},
        ]
    }

    assert masked["sources"][0]["api_token"] == "***"
    merged = merge_preserving_secrets(existing, reordered)
    assert merged["sources"][0]["source"] == "rtsp://bob:secret-b@camera/b"
    assert merged["sources"][0]["api_token"] == "token-b"
    assert merged["sources"][1]["source"] == "rtsp://alice:secret-a@camera/a"
    assert merged["sources"][1]["api_token"] == "token-a"


def test_operation_worker_is_dispatched_detached_from_the_web_process(tmp_path: Path, monkeypatch):
    from evileye.core import extension_builder
    from evileye.service_manager import state as service_state
    from evileye import stack_control

    captured = {}
    monkeypatch.setattr(service_state, "load_state", lambda _root: {})
    monkeypatch.setattr(stack_control, "is_in_container", lambda: False)
    monkeypatch.setattr(extension_builder.subprocess, "Popen", lambda args, **options: captured.update(args=args, options=options))

    assert extension_builder.dispatch_plugin_service_restart("12345678-abcd", tmp_path) is True
    assert "evileye.core.plugin_operation_worker" in captured["args"]
    assert captured["options"]["stdin"] is extension_builder.subprocess.DEVNULL
    if not __import__("sys").platform.startswith("win"):
        assert captured["options"]["start_new_session"] is True


def test_restart_operation_is_reconciled_after_backend_startup(tmp_path: Path):
    from evileye.core import extension_builder

    record = {
        "id": "12345678-abcd",
        "status": "restarting",
        "name": "sample",
        "plugin_id": "sample",
        "template": "processor",
        "created_at": 1,
        "updated_at": 1,
    }
    extension_builder._store_operation(record, tmp_path)
    extension_builder.reconcile_plugin_operations(root=tmp_path)
    updated = get_plugin_operation(record["id"], root=tmp_path)
    assert updated["status"] == "completed"


@pytest.mark.parametrize(
    ("restart_ok", "web_ready", "expected"),
    [(True, True, "completed"), (True, False, "pending_restart"), (False, False, "pending_restart")],
)
def test_managed_service_restart_records_result_and_readiness(tmp_path: Path, monkeypatch, restart_ok, web_ready, expected):
    from types import SimpleNamespace

    from evileye import service_manager, stack_control
    from evileye.core import extension_builder

    record = {
        "id": "87654321-abcd",
        "status": "installed",
        "name": "restart-check",
        "plugin_id": "restart_check",
        "template": "processor",
        "created_at": 1,
        "updated_at": 1,
    }
    extension_builder._store_operation(record, tmp_path)
    monkeypatch.setattr(service_manager, "control_service", lambda *_args, **_kwargs: SimpleNamespace(ok=restart_ok, message="service error"))
    monkeypatch.setattr(service_manager.state, "load_state", lambda _root: {"port": 8181})
    monkeypatch.setattr(stack_control, "wait_web_ready", lambda **_kwargs: web_ready)

    extension_builder.restart_plugin_service(record["id"], tmp_path)

    stored = get_plugin_operation(record["id"], root=tmp_path)
    assert stored["status"] == expected
