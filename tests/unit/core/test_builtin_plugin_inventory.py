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

_BUILTIN_CONTRACTS = {
    "AttributeClassifier": ("processor_item", ("thread", "process")),
    "AttributeDetector": ("processor_item", ("thread", "process")),
    "AttributeEventsDetector": ("event_detector", ("process",)),
    "CamEventsDetector": ("event_detector", ("process",)),
    "FieldOfViewEventsDetector": ("event_detector", ("process",)),
    "ObjectDetectorRfdetr": ("processor_item", ("thread", "process")),
    "ObjectDetectorRtdetr": ("processor_item", ("thread", "process")),
    "ObjectDetectorYolo": ("processor_item", ("thread", "process")),
    "ObjectMultiCameraTracking": ("batch_processor", ("thread",)),
    "ObjectTrackingBotsort": ("processor_item", ("thread", "process")),
    "PreprocessingPipeline": ("processor_item", ("thread", "process")),
    "RoiFeeder": ("processor_item", ("thread", "process")),
    "ScheduleAlarmEventsDetector": ("event_detector", ("process",)),
    "SystemEventsDetector": ("event_detector", ("process",)),
    "VideoCaptureGStreamer": ("source", ("thread", "process")),
    "VideoCaptureOpencv": ("source", ("thread", "process")),
    "ZoneEventsDetector": ("event_detector", ("process",)),
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

    builtin_ids = {
        module_id
        for module_id in registered_ids
        if (registered := plugin_registry.get_module(module_id)) is not None
        and registered.plugin_id == "evileye"
        and getattr(registered.spec.factory, "__module__", "").startswith("evileye.")
    }
    expected_builtin_ids = {
        f"evileye/{module_id}" for module_id in _BUILTIN_CONTRACTS
    }
    assert builtin_ids == expected_builtin_ids

    for module_name, (expected_kind, expected_modes) in _BUILTIN_CONTRACTS.items():
        registered = plugin_registry.get_module(module_name)
        assert registered is not None
        assert registered.spec.kind == expected_kind
        assert tuple(registered.spec.execution_modes) == expected_modes

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

    from evileye.core.plugin_runtime import ParallelItemModuleAdapter

    adapter = EvilEyeBase.create_instance("ObjectDetectorYoloMp")
    assert isinstance(adapter, ParallelItemModuleAdapter)
    adapter.set_params(
        type="ObjectDetectorYoloMp",
        execution_mode="thread",
        source_ids=[0],
        num_detection_threads=2,
    )
    assert adapter.execution_mode == "thread"
    assert adapter.worker_count == 2
    assert adapter.registered_module.spec.factory.__name__ == "ObjectDetectorYolo"


def test_builtin_inventory_has_no_legacy_processor_or_source_protocols():
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
    assert legacy_modules == set()
    for module_id in ("VideoCaptureOpencv", "VideoCaptureGStreamer"):
        source = plugin_registry.get_module(module_id)
        assert source is not None
        assert "capture_source_backend" in source.spec.capabilities
        assert "legacy_source_protocol" not in source.spec.capabilities


def test_rfdetr_legacy_thread_count_maps_to_ordered_item_workers():
    from evileye.core.plugin_runtime import ParallelItemModuleAdapter

    adapter = EvilEyeBase.create_instance("ObjectDetectorRfdetr")
    assert isinstance(adapter, ParallelItemModuleAdapter)
    adapter.set_params(
        module_id="ObjectDetectorRfdetr",
        execution_mode="thread",
        source_ids=[0],
        num_detection_threads=4,
    )
    assert adapter.worker_count == 4
