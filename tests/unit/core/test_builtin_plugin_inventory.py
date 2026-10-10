"""Inventory gate for built-in modules migrating to PluginRegistry."""

import evileye.attributes_detection  # noqa: F401
import evileye.capture  # noqa: F401
import evileye.object_detector  # noqa: F401
import evileye.object_tracker  # noqa: F401
import evileye.object_multi_camera_tracker  # noqa: F401
import evileye.preprocessing  # noqa: F401

from evileye.core.base_class import EvilEyeBase
from evileye.core.plugins import EXECUTION_MODES, MODULE_KINDS, plugin_registry
from evileye.events_detectors.event_registry import register_builtins


_BUILTIN_MODULES = {
    "AttributeClassifier",
    "AttributeDetector",
    "AttributeEventsDetector",
    "CamEventsDetector",
    "FieldOfViewEventsDetector",
    "ObjectDetectorRfdetr",
    "ObjectDetectorRtdetr",
    "ObjectDetectorYolo",
    "ObjectDetectorYoloMp",
    "ObjectMultiCameraTracking",
    "ObjectTrackingBotsort",
    "PreprocessingPipeline",
    "RoiFeeder",
    "ScheduleAlarmEventsDetector",
    "SystemEventsDetector",
    "VideoCaptureGStreamer",
    "VideoCaptureOpencv",
    "ZoneEventsDetector",
}


def test_all_builtin_modules_are_resolved_from_plugin_registry():
    register_builtins()
    registered_ids = set(plugin_registry.list_modules())
    missing = {
        module_id
        for module_id in _BUILTIN_MODULES
        if plugin_registry.get_module(module_id) is None
    }
    assert not missing, f"Built-in modules missing from PluginRegistry: {sorted(missing)}"

    for module_id in registered_ids:
        registered = plugin_registry.get_module(module_id)
        assert registered is not None
        assert registered.spec.kind in MODULE_KINDS
        modes = set(registered.spec.execution_modes)
        assert modes and modes <= EXECUTION_MODES
        assert callable(registered.spec.factory)

    batch = plugin_registry.get_module("ObjectMultiCameraTracking")
    assert batch is not None
    assert batch.spec.kind == "batch_processor"
    assert tuple(batch.spec.execution_modes) == ("thread",)


def test_yolo_mp_config_name_resolves_to_canonical_yolo_module():
    register_builtins()
    canonical = plugin_registry.get_module("ObjectDetectorYolo")
    compatibility = plugin_registry.get_module("ObjectDetectorYoloMp")

    assert canonical is not None
    assert compatibility is canonical
    assert compatibility.spec.factory.__name__ == "ObjectDetectorYolo"
    assert "evileye/ObjectDetectorYoloMp" not in plugin_registry.list_modules()

    adapter = EvilEyeBase.create_instance("ObjectDetectorYoloMp")
    adapter.set_params(
        type="ObjectDetectorYoloMp",
        execution_mode="thread",
        source_ids=[0],
    )
    assert adapter.execution_mode == "thread"
    assert adapter._module.__class__.__name__ == "ObjectDetectorYolo"
    assert adapter._module.execution_mode == "thread"


def test_legacy_protocols_are_explicitly_tracked_during_migration():
    register_builtins()
    legacy_modules = {
        module_id
        for module_id in plugin_registry.list_modules()
        if (registered := plugin_registry.get_module(module_id)) is not None
        and registered.plugin_id == "evileye"
        and (
            "legacy_processor_protocol" in registered.spec.capabilities
            or "legacy_source_protocol" in registered.spec.capabilities
        )
    }
    assert legacy_modules == {
        "evileye/AttributeClassifier",
        "evileye/AttributeDetector",
        "evileye/ObjectDetectorRfdetr",
        "evileye/ObjectDetectorRtdetr",
        "evileye/ObjectDetectorYolo",
        "evileye/VideoCaptureGStreamer",
        "evileye/VideoCaptureOpencv",
    }
