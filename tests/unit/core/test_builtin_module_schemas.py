import pytest

from evileye.core.builtin_inventory import register_builtins
from evileye.core.plugins import PluginError, plugin_registry


def test_every_builtin_module_has_display_metadata_and_a_form_schema():
    register_builtins()
    from evileye.core.builtin_module_schemas import BUILTIN_MODULE_SCHEMAS

    registered = {
        module_id: item for module_id in plugin_registry.list_modules()
        if (item := plugin_registry.get_module(module_id)) is not None
        and item.plugin_id == "evileye"
        and item.spec.factory.__module__.startswith("evileye.")
    }
    assert set(registered) == {f"evileye/{module_id}" for module_id in BUILTIN_MODULE_SCHEMAS}
    builtin = list(registered.values())
    assert len(builtin) >= 17
    assert all(item is not None and item.plugin_id == "evileye" for item in builtin)
    assert all(item.spec.display_name for item in builtin)
    assert all(item.spec.description for item in builtin)
    assert all(isinstance(item.spec.config_schema, dict) for item in builtin)
    assert all(item.spec.stages for item in builtin)


def test_builtin_schema_checks_types_ranges_and_enum_but_preserves_unknown_fields():
    register_builtins()
    valid = {"model": "models/yolo.pt", "conf": 0.5, "classes": [0], "legacy_extension": {"x": 1}}
    normalized = plugin_registry.validate_module_config("ObjectDetectorYolo", valid)
    assert normalized == valid
    with pytest.raises(PluginError, match="conf must be <= 1"):
        plugin_registry.validate_module_config("ObjectDetectorYolo", {"conf": 1.5})
    with pytest.raises(PluginError, match="execution_mode must be one of"):
        plugin_registry.validate_module_config("ObjectDetectorYolo", {"execution_mode": "gpu"})


def test_builtin_pipeline_config_schema_rejects_invalid_fanout_values():
    register_builtins()
    for policy in ("forward_partial", "drop_frame"):
        assert plugin_registry.validate_pipeline_config(
            "PipelineSurveillance", {"detector_fanout_policy": policy},
        ) == {"detector_fanout_policy": policy}
    with pytest.raises(PluginError, match="detector_fanout_policy"):
        plugin_registry.validate_pipeline_config("PipelineSurveillance", {"detector_fanout_policy": "wait_all"})
    with pytest.raises(PluginError, match="detector_fanout_timeout_sec must be > 0"):
        plugin_registry.validate_pipeline_config(
            "PipelineSurveillance", {"detector_fanout_timeout_sec": 0}
        )


def test_builtin_pipelines_declare_configuration_and_topology_metadata():
    register_builtins()
    for pipeline_id in ("PipelineSurveillance", "PipelineDeclarative", "PipelineCapture"):
        registered = plugin_registry.get_pipeline(pipeline_id)
        assert registered is not None
        assert isinstance(registered.spec.config_schema, dict)
        assert callable(registered.spec.topology_provider)


def test_topology_uses_builtin_module_display_names():
    from evileye.core.pipeline_topology import build_topology

    topology = build_topology({"pipeline": {"pipeline_class": "PipelineSurveillance", "detectors": [
        {"type": "ObjectDetectorYolo"},
    ]}})

    detector = next(node for node in topology.nodes if node.stage == "Detectors")
    assert detector.label == "YOLO detector [1]"


def test_legacy_source_config_shapes_with_nulls_and_split_coordinates_are_valid():
    register_builtins()
    source_config = {
        "source": "VideoFile",
        "camera": "sample.mp4",
        "num_split": None,
        "src_coords": [[0, 0, 1920, 1080], [0, 1080, 1920, 1080]],
        "desired_fps": None,
        "source_ids": [0],
    }
    assert plugin_registry.validate_module_config("VideoCaptureOpencv", source_config) == source_config


def test_builtin_form_schemas_cover_legacy_fields_in_repository_configs():
    register_builtins()
    source_config = {"fps": 20, "source_fps": 15}
    detector_config = {"conf_thresh": 0.4}
    video_path_config = {"type": "video_file", "path": "videos/test.mp4"}
    legacy_tracker_config = {
        "type": "botsort", "track_thresh": 0.5,
        "match_thresh": 0.8, "num_tracking_threads": 1,
    }

    assert plugin_registry.validate_module_config("VideoCaptureOpencv", source_config) == source_config
    assert plugin_registry.validate_module_config("ObjectDetectorYolo", detector_config) == detector_config
    assert plugin_registry.validate_module_config("VideoCaptureOpencv", video_path_config) == video_path_config
    assert plugin_registry.validate_module_config("ObjectTrackingBotsort", legacy_tracker_config) == legacy_tracker_config


def test_builtin_form_schemas_cover_fields_used_by_checked_in_configs():
    import json
    from pathlib import Path

    from evileye.core.builtin_module_schemas import BUILTIN_MODULE_SCHEMAS

    root = Path(__file__).resolve().parents[3]
    stage_modules = {
        "sources": ("VideoCaptureOpencv", "VideoCaptureGStreamer"),
        "preprocessors": ("PreprocessingPipeline",),
        "detectors": ("ObjectDetectorYolo", "ObjectDetectorRtdetr", "ObjectDetectorRfdetr"),
        "trackers": ("ObjectTrackingBotsort",),
        "mc_trackers": ("ObjectMultiCameraTracking",),
        "attributes_roi": ("RoiFeeder", "AttributeDetector"),
        "attributes_classifier": ("AttributeClassifier", "AttributeDetector"),
    }
    fields_by_module = {module_id: set() for module_id in BUILTIN_MODULE_SCHEMAS}

    def add_items(module_ids, items):
        if not isinstance(items, list):
            return
        for item in items:
            if not isinstance(item, dict):
                continue
            module_id = str(item.get("module_id") or item.get("type") or "").split("/")[-1]
            if module_id not in module_ids:
                module_id = module_ids[0]
            if module_id in fields_by_module:
                fields_by_module[module_id].update(item)

    for path in (root / "configs").rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        pipeline = data.get("pipeline", data)
        if not isinstance(pipeline, dict):
            continue
        for stage, module_ids in stage_modules.items():
            add_items(module_ids, pipeline.get(stage))
            modules = pipeline.get("modules")
            extension = modules.get(stage) if isinstance(modules, dict) else None
            if isinstance(extension, dict):
                add_items(module_ids, extension.get("items"))
        events = data.get("events_detectors")
        if isinstance(events, dict):
            for module_id, item in events.items():
                if module_id == "enabled" or not isinstance(item, dict):
                    continue
                module_id = str(item.get("module_id") or module_id).split("/")[-1]
                if module_id in fields_by_module:
                    fields_by_module[module_id].update(item)

    uncovered = {
        module_id: sorted(fields - set(BUILTIN_MODULE_SCHEMAS[module_id].get("properties", {})))
        for module_id, fields in fields_by_module.items()
        if fields - set(BUILTIN_MODULE_SCHEMAS[module_id].get("properties", {}))
    }
    assert not uncovered, f"Built-in configuration fields missing form schemas: {uncovered}"


def test_source_schema_checks_nested_capture_and_recording_fields():
    register_builtins()
    config = {
        "capture": {"queue_size": 4, "ignore_udp_stream_errors": True},
        "record": {"enabled": True, "segment_length_sec": 60, "event_buffer_fps": None},
    }
    assert plugin_registry.validate_module_config("VideoCaptureOpencv", config) == config
    with pytest.raises(PluginError, match="config.capture.queue_size must be >= 1"):
        plugin_registry.validate_module_config("VideoCaptureOpencv", {"capture": {"queue_size": 0}})
    with pytest.raises(PluginError, match="config.record.min_free_space_pct must be <= 100"):
        plugin_registry.validate_module_config("VideoCaptureOpencv", {"record": {"min_free_space_pct": 120}})


def test_tracker_schema_covers_boost_configuration_fields():
    register_builtins()
    config = {"botsort_cfg": {"fuse_score": True, "with_reid": False}}
    assert plugin_registry.validate_module_config("ObjectTrackingBotsort", config) == config


def test_module_execution_mode_is_checked_against_declared_capabilities():
    register_builtins()
    process_only = next(
        module_id for module_id in plugin_registry.list_modules()
        if tuple(plugin_registry.get_module(module_id).spec.execution_modes) == ("process",)
    )

    with pytest.raises(PluginError, match="execution_mode must be one of"):
        plugin_registry.validate_module_config(process_only, {"execution_mode": "thread"})
