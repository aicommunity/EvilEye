import json
from pathlib import Path
import pytest

from evileye.cli_commands.pipeline_configure import (
    BACKUP_LIMIT,
    _diff,
    _write_config_with_backup,
    configure_pipeline,
)


def test_config_save_creates_backup_and_does_not_rewrite_identical_content(tmp_path: Path):
    path = tmp_path / "site.json"
    path.write_text('{"value": 1}\n', encoding="utf-8")
    backup = _write_config_with_backup(path, '{"value": 2}\n')
    assert backup is not None
    assert json.loads(backup.read_text(encoding="utf-8")) == {"value": 1}
    assert path.read_text(encoding="utf-8") == '{"value": 2}\n'
    assert _write_config_with_backup(path, '{"value": 2}\n') is None
    assert len(list(tmp_path.glob("site.json.bak.*"))) == 1


def test_config_save_rotates_to_the_latest_ten_backups(tmp_path: Path):
    path = tmp_path / "site.json"
    path.write_text('{"version": 0}\n', encoding="utf-8")
    for version in range(1, BACKUP_LIMIT + 5):
        _write_config_with_backup(path, json.dumps({"version": version}) + "\n")
    backups = list(tmp_path.glob("site.json.bak.*"))
    assert len(backups) == BACKUP_LIMIT
    assert json.loads(path.read_text(encoding="utf-8")) == {"version": BACKUP_LIMIT + 4}


def test_diff_redacts_secret_values_but_reports_the_field():
    text = _diff({"password": "old-secret", "camera": {"username": "user"}},
                 {"password": "new-secret", "camera": {"username": "admin"}})
    assert "password" in text
    assert "username" in text
    assert "old-secret" not in text and "new-secret" not in text
    assert '"user"' not in text and '"admin"' not in text


def test_camera_url_credentials_are_masked_in_diff_and_form_values():
    from evileye.cli_commands.pipeline_configure import _diff, _safe_form_value

    old_url = "rtsp://operator:old-secret@camera.local:8554/live"
    new_url = "rtsp://admin:new-secret@camera.local:8554/live"
    text = _diff({"camera": old_url}, {"camera": new_url})
    displayed = _safe_form_value("camera", old_url, {"type": "string"})

    assert "old-secret" not in text and "new-secret" not in text
    assert "operator" not in text and "admin" not in text
    assert "old-secret" not in displayed and "operator" not in displayed
    assert "camera.local:8554" in displayed


def test_secret_prompt_does_not_echo_existing_url_and_keeps_it_on_empty(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard

    captured = {}

    def ask(_label, **options):
        captured.update(options)
        return ""

    monkeypatch.setattr(wizard.Prompt, "ask", ask)
    value = "rtsp://operator:secret@camera.local/live"
    result = wizard._prompt_field("camera", {"type": "string"}, value, present=True)

    assert result == (True, value)
    assert captured["password"] is True
    assert captured["default"] == ""


def test_builtin_module_choices_are_filtered_by_declared_pipeline_stage():
    from evileye.core.builtin_inventory import register_builtins
    from evileye.cli_commands.pipeline_configure import _available_modules

    register_builtins()
    detector_ids = {module_id for module_id, _ in _available_modules("processor_item", "detectors")}
    source_ids = {module_id for module_id, _ in _available_modules("source", "sources")}
    declarative_source_ids = {module_id for module_id, _ in _available_modules("source", "source")}

    assert "evileye/ObjectDetectorYolo" in detector_ids
    assert "evileye/ObjectTrackingBotsort" not in detector_ids
    assert source_ids == {"evileye/VideoCaptureOpencv", "evileye/VideoCaptureGStreamer"}
    assert declarative_source_ids == source_ids


def test_builtin_pipeline_form_exposes_pipeline_specific_settings():
    from evileye.core.builtin_inventory import register_builtins
    from evileye.cli_commands.pipeline_configure import _pipeline_form_fields

    register_builtins()
    surveillance = _pipeline_form_fields("PipelineSurveillance", {
        "sources", "preprocessors", "detectors", "trackers", "mc_trackers",
        "attributes_roi", "attributes_classifier", "modules",
    })
    declarative = _pipeline_form_fields("PipelineDeclarative", {"stages"})

    assert set(surveillance) == {
        "detector_fanout_policy", "detector_fanout_timeout_sec",
        "detector_fanout_max_pending",
    }
    assert set(declarative) == {"final_results"}


def test_event_config_list_preserves_enabled_control_and_toggles_modules(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard

    root = {"events_detectors": {
        "enabled": ["CamEventsDetector"],
        "CamEventsDetector": {},
        "vendor/safety-rule": {"module_id": "vendor/safety-rule"},
    }}
    captured = {}

    def edit_list(_group, _title, _kind, _fallback, get_items, set_items, **options):
        entries = get_items()
        assert [identity for identity, _item in entries] == [
            "CamEventsDetector", "vendor/safety-rule",
        ]
        captured["is_enabled"] = options["is_enabled"]
        captured["toggle_enabled"] = options["toggle_enabled"]
        entries.append(("vendor/new-rule", {"module_id": "vendor/new-rule"}))
        set_items(entries)

    monkeypatch.setattr(wizard, "_edit_list", edit_list)
    wizard._configure_events(root)
    assert root["events_detectors"]["enabled"] == [
        "CamEventsDetector", "vendor/new-rule",
    ]
    captured["toggle_enabled"]("vendor/safety-rule", root["events_detectors"]["vendor/safety-rule"])
    assert root["events_detectors"]["enabled"] == [
        "CamEventsDetector", "vendor/new-rule", "vendor/safety-rule",
    ]
    captured["toggle_enabled"]("CamEventsDetector", root["events_detectors"]["CamEventsDetector"])
    assert root["events_detectors"]["enabled"] == ["vendor/new-rule", "vendor/safety-rule"]


def test_event_wizard_exposes_default_enabled_rules_and_can_disable_one(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard
    from evileye.events_detectors.event_registry import DEFAULT_ENABLED_EVENT_DETECTORS

    root = {}
    captured = {}

    def edit_list(_group, _title, _kind, _fallback, get_items, set_items, **options):
        entries = get_items()
        assert [identity for identity, _item in entries] == list(DEFAULT_ENABLED_EVENT_DETECTORS)
        assert all(options["is_enabled"](identity, item) for identity, item in entries)
        captured["toggle_enabled"] = options["toggle_enabled"]
        entries = entries[1:]
        set_items(entries)

    monkeypatch.setattr(wizard, "_edit_list", edit_list)
    wizard._configure_events(root)

    assert root["events_detectors"]["enabled"] == list(DEFAULT_ENABLED_EVENT_DETECTORS[1:])
    captured["toggle_enabled"](DEFAULT_ENABLED_EVENT_DETECTORS[1], {})
    assert DEFAULT_ENABLED_EVENT_DETECTORS[1] not in root["events_detectors"]["enabled"]


def test_event_validator_ignores_root_enabled_control_list():
    from evileye.cli_commands.pipeline_configure import validate_configuration
    from evileye.core.builtin_inventory import register_builtins

    register_builtins()
    diagnostics = validate_configuration({"events_detectors": {
        "enabled": ["CamEventsDetector"],
        "CamEventsDetector": {},
    }})
    assert not any("unknown module 'enabled'" in issue for issue in diagnostics)


def test_event_validator_reports_invalid_or_unknown_enabled_detectors():
    from evileye.cli_commands.pipeline_configure import validate_configuration
    from evileye.core.builtin_inventory import register_builtins

    register_builtins()
    invalid_type = validate_configuration({"events_detectors": {"enabled": "CamEventsDetector"}})
    assert any("events_detectors.enabled must be an array" in issue for issue in invalid_type)

    unknown = validate_configuration({"events_detectors": {"enabled": ["vendor/missing"]}})
    assert any("unknown event detector 'vendor/missing'" in issue for issue in unknown)


def test_configure_shows_diff_then_saves_with_backup_after_confirmation(tmp_path: Path, monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard
    import evileye.core.builtin_inventory as inventory

    path = tmp_path / "config.json"
    original = {"pipeline": {"pipeline_class": "PipelineSurveillance", "sources": []}}
    path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(inventory, "register_builtins", lambda: None)
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: "__done__")
    monkeypatch.setattr(wizard, "_configure_events", lambda root: root.update(events_detectors={"vendor/alarm": {"enabled": True}}))
    monkeypatch.setattr(wizard, "validate_configuration", lambda _config: [])
    monkeypatch.setattr(wizard, "Confirm", type("ConfirmStub", (), {"ask": staticmethod(lambda *_args, **_kwargs: True)}))
    monkeypatch.setattr("evileye.cli_interactive.interactive_available", lambda: True)

    configure_pipeline(str(path))

    saved = json.loads(path.read_text(encoding="utf-8"))
    assert saved["events_detectors"]["vendor/alarm"]["enabled"] is True
    backups = list(tmp_path.glob("config.json.bak.*"))
    assert len(backups) == 1
    assert json.loads(backups[0].read_text(encoding="utf-8")) == original


def test_configure_refusal_keeps_original_file_and_creates_no_backup(tmp_path: Path, monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard
    import evileye.core.builtin_inventory as inventory

    path = tmp_path / "config.json"
    original = {"pipeline": {"pipeline_class": "PipelineSurveillance", "sources": []}}
    content = json.dumps(original, indent=2) + "\n"
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr(inventory, "register_builtins", lambda: None)
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: "__done__")
    monkeypatch.setattr(wizard, "_configure_events", lambda root: root.update(events_detectors={"vendor/alarm": {"enabled": True}}))
    monkeypatch.setattr(wizard, "validate_configuration", lambda _config: [])
    monkeypatch.setattr(wizard, "Confirm", type("ConfirmStub", (), {"ask": staticmethod(lambda *_args, **_kwargs: False)}))
    monkeypatch.setattr("evileye.cli_interactive.interactive_available", lambda: True)

    configure_pipeline(str(path))

    assert path.read_text(encoding="utf-8") == content
    assert not list(tmp_path.glob("config.json.bak.*"))


def test_field_prompt_retries_bounds_and_nested_types(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard

    inputs = iter(["-1", "3", '{"queue_size": "wrong"}', '{"queue_size": 4}'])
    monkeypatch.setattr(wizard.Prompt, "ask", lambda *_args, **_kwargs: next(inputs))
    assert wizard._prompt_field("workers", {"type": "integer", "minimum": 1}) == (True, 3)
    assert wizard._prompt_field("capture", {
        "type": "object", "properties": {"queue_size": {"type": "integer", "minimum": 1}},
    }) == (True, {"queue_size": 4})


def test_blank_optional_object_is_not_inserted_as_invalid_null(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard

    monkeypatch.setattr(wizard.Prompt, "ask", lambda *_args, **_kwargs: "")
    assert wizard._prompt_field("capture", {"type": "object"}) == (False, None)


def test_cancelled_module_form_aborts_editor_without_applying_changes(monkeypatch):
    import evileye.cli_commands.pipeline_configure as wizard
    from evileye.cli_interactive import InteractiveInputError

    choices = iter(["add", "vendor/module"])
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(wizard, "_available_modules", lambda *_args: [("vendor/module", "Example")])
    monkeypatch.setattr(wizard, "edit_module_form", lambda *_args: (_ for _ in ()).throw(InteractiveInputError("cancelled")))
    writes = []
    with pytest.raises(InteractiveInputError):
        wizard._edit_list("detectors", "Detectors", "processor_item", None, lambda: [], writes.append)
    assert writes == []


def test_invalid_enabled_detector_cannot_be_saved(tmp_path, monkeypatch):
    import typer
    import evileye.cli_commands.pipeline_configure as wizard
    from evileye.core.builtin_inventory import register_builtins

    register_builtins()
    path = tmp_path / "invalid.json"
    content = json.dumps({"pipeline": {"pipeline_class": "PipelineSurveillance"}, "events_detectors": {"enabled": ["missing/alarm"]}})
    path.write_text(content, encoding="utf-8")
    monkeypatch.setattr("evileye.cli_interactive.interactive_available", lambda: True)
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: "__done__")
    monkeypatch.setattr(wizard, "_configure_events", lambda _root: None)
    monkeypatch.setattr(wizard, "_confirm", lambda *_args, **_kwargs: pytest.fail("invalid config must not ask to save"))
    with pytest.raises(typer.Exit) as error:
        wizard.configure_pipeline(str(path))
    assert error.value.exit_code == 1
    assert path.read_text(encoding="utf-8") == content
    assert not list(tmp_path.glob("*.bak.*"))


def test_legacy_declarative_form_preserves_noop_and_edits_effective_stages(monkeypatch):
    import copy
    import evileye.cli_commands.pipeline_configure as wizard

    pipeline = {"pipeline_class": "PipelineDeclarative", "sources": [{"camera": "file.mp4"}], "detectors": [{"model": "old.pt"}]}
    original = copy.deepcopy(pipeline)
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: "__back__")
    wizard._configure_declarative(pipeline)
    assert pipeline == original
    selections = iter(["1", "__back__"])
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: next(selections))
    def edit(_group, _title, _kind, _fallback, get_items, set_items, **_kwargs):
        entries = get_items()
        entries[0][1]["model"] = "new.pt"
        set_items(entries)
    monkeypatch.setattr(wizard, "_edit_list", edit)
    wizard._configure_declarative(pipeline)
    assert [stage["name"] for stage in pipeline["stages"]] == ["sources", "detectors"]
    assert pipeline["stages"][1]["items"][0]["model"] == "new.pt"
    assert pipeline["detectors"] == original["detectors"]


def test_plugin_declared_secret_fields_are_redacted_from_diff():
    import uuid
    from evileye.core.plugins import PluginSpec, ModuleSpec, PLUGIN_API_VERSION, plugin_registry

    plugin_registry.register_plugin(PluginSpec(
        "test.secret." + uuid.uuid4().hex, PLUGIN_API_VERSION,
        modules=(ModuleSpec("module", "processor_item", dict, config_schema={
            "type": "object", "properties": {"access_code": {"type": "string", "writeOnly": True}},
        }),),
    ))
    diff = _diff({"access_code": "old-private-value"}, {"access_code": "new-private-value"})
    assert "old-private-value" not in diff and "new-private-value" not in diff
    assert "previous" in diff and "proposed" in diff


def test_uri_credential_change_is_visible_without_printing_credentials():
    text = _diff({"endpoint": "rtsp://user:old-password@camera/live"},
                 {"endpoint": "rtsp://user:new-password@camera/live"})
    assert "old-password" not in text and "new-password" not in text
    assert "previous credentials" in text and "proposed credentials" in text


@pytest.mark.parametrize("error", [EOFError, KeyboardInterrupt])
def test_form_eof_and_interrupt_cancel_configuration(monkeypatch, error):
    import evileye.cli_commands.pipeline_configure as wizard
    from evileye.cli_interactive import InteractiveInputError

    def ask(*_args, **_kwargs):
        raise error()
    monkeypatch.setattr(wizard.Prompt, "ask", ask)
    with pytest.raises(InteractiveInputError):
        wizard._prompt_field("workers", {"type": "integer"})


def test_declarative_validation_checks_stage_names_and_result_reference():
    from evileye.cli_commands.pipeline_configure import validate_configuration

    config = {"pipeline": {"pipeline_class": "PipelineDeclarative", "stages": [
        {"name": "rules", "kind": "step", "items": [{}]},
    ], "final_results": "missing"}, "events_detectors": {"enabled": []}}
    assert any("final_results references an unknown stage" in issue for issue in validate_configuration(config))
    config["pipeline"]["final_results"] = "rules"
    assert validate_configuration(config) == []
    config["pipeline"]["stages"].append({"name": "rules", "kind": "step", "items": [{}]})
    assert any("Duplicate pipeline stage name" in issue for issue in validate_configuration(config))


def test_strict_plugin_schema_accepts_runtime_envelope_and_form_edits_nested_payload(monkeypatch):
    import uuid
    import time
    import evileye.cli_commands.pipeline_configure as wizard
    from evileye.core.plugins import PluginSpec, ModuleSpec, PLUGIN_API_VERSION, plugin_registry
    from evileye.core.base_class import EvilEyeBase
    from tests.unit.pipeline.plugin_detector_fixtures import ConfigEchoProcessor

    plugin_id = "test.strict.form." + uuid.uuid4().hex
    module_id = plugin_id + "/rule"
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(
        ModuleSpec("rule", "processor_item", ConfigEchoProcessor, config_schema={
            "type": "object", "properties": {"threshold": {"type": "number"}},
            "required": ["threshold"], "additionalProperties": False,
        }),
    )))
    item = {"module_id": module_id, "execution_mode": "thread", "source_ids": [0], "worker_count": 1, "config": {"threshold": 0.5}}
    config = {"pipeline": {"detectors": [item]}, "events_detectors": {"enabled": []}}
    assert wizard.validate_configuration(config) == []
    choices = iter(["threshold", "__done__"])
    monkeypatch.setattr(wizard, "_choose", lambda *_args, **_kwargs: next(choices))
    monkeypatch.setattr(wizard, "_prompt_field", lambda *_args, **_kwargs: (True, 0.8))
    edited = wizard.edit_module_form(module_id, item)
    assert edited["config"] == {"threshold": 0.8}
    assert "threshold" not in edited
    assert item["config"] == {"threshold": 0.5}
    config["pipeline"]["detectors"] = [edited]
    assert wizard.validate_configuration(config) == []
    adapter = EvilEyeBase.create_instance(module_id)
    adapter.set_params(**edited)
    assert adapter.init()
    try:
        adapter.start()
        assert adapter.is_ready(2)
        adapter.put("audit")
        deadline = time.monotonic() + 2
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            time.sleep(0.005)
        assert result == {"threshold": 0.8}
    finally:
        adapter.stop()
        adapter.release()
    edited["source_ids"] = "invalid"
    assert any("source_ids must be array" in issue for issue in wizard.validate_configuration(config))
