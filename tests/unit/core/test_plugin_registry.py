from __future__ import annotations

import logging
import pickle
import threading
import time

import pytest

from evileye.core.plugin_runtime import (
    BatchProcessorModuleAdapter,
    ItemModuleAdapter,
    ItemModuleWorker,
    LegacyProcessorModuleAdapter,
    SourceModuleAdapter,
)
from evileye.core.processor_source import ProcessorSource
from evileye.core.base_class import EvilEyeBase
from evileye.core.interfaces import (
    IBatchProcessor,
    IContextualStatefulItemProcessor,
    IItemProcessor,
    IModelClassMappingProvider,
    IRuntimeStatusProvider,
    ISource,
    IStatefulItemProcessor,
)
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginError,
    PluginManager,
    PluginRegistry,
    PluginSpec,
    RegisteredModule,
    plugin_registry,
)


class _EntryPoint:
    def __init__(self, name, factory):
        self.name = name
        self.value = f"test:{name}"
        self._factory = factory

    def load(self):
        return self._factory


class _BrokenEntryPoint:
    name = "broken-plugin"
    value = "missing:load_plugin"

    def load(self):
        raise ImportError("plugin dependency is missing")


class _EchoItemModule:
    def __init__(self, config=None):
        self.prefix = (config or {}).get("prefix", "")

    def create_state(self, config):
        return {"count": 0}

    def process_item(self, item, state):
        state["count"] += 1
        return f"{self.prefix}{item}:{state['count']}"


class _ContextItemModule:
    def create_state(self, config, context):
        return {"count": 0, "context": context}

    def process_item(self, item, state):
        state["count"] += 1
        context = state["context"]
        return {
            "item": item,
            "count": state["count"],
            "module_id": context.module_id,
            "execution_mode": context.execution_mode,
            "source_ids": context.source_ids,
        }


class _LateModelMappingItemModule:
    def __init__(self, config=None):
        self.mapping = dict((config or {}).get("model_class_mapping", {}))
        self.loaded = False

    def create_state(self, config):
        return {"loaded": False}

    def process_item(self, item, state):
        state["loaded"] = True
        self.loaded = True
        return item

    def get_model_class_mapping(self):
        return self.mapping if self.loaded else None


class _EchoBatchModule:
    def __init__(self, config=None):
        self.prefix = (config or {}).get("prefix", "")

    def create_state(self, config):
        return {"count": 0}

    def process_batch(self, batch, state):
        state["count"] += 1
        return [f"{self.prefix}{source_id}:{len(items)}:{state['count']}" for source_id, items in batch.items()]


class _SequenceSource:
    def __init__(self, config=None):
        self.items = list((config or {}).get("items", []))
        self.index = 0
        self.closed = False

    def open(self):
        self.index = 0

    def read(self):
        if self.index >= len(self.items):
            return None
        item = self.items[self.index]
        self.index += 1
        return item

    def close(self):
        self.closed = True


class _FailingSource:
    def __init__(self, config=None):
        self.read_count = 0

    def open(self):
        pass

    def read(self):
        self.read_count += 1
        if self.read_count == 1:
            return {"frame_id": 1}
        raise RuntimeError("intentional source failure")

    def close(self):
        pass


class _UnpicklableOutputSource:
    def __init__(self, config=None):
        pass

    def open(self):
        pass

    def read(self):
        return lambda: "not serializable"

    def close(self):
        pass


class _UnpicklableOutputModule:
    def process_item(self, item, state):
        return lambda: item


class _ProcessQueueSink:
    def __init__(self):
        self.items = []

    def put(self, item, **kwargs):
        self.items.append(item)


class _FailingItemModule:
    def process_item(self, item, state):
        raise RuntimeError("intentional test failure")


class _FailingStateItemModule:
    def create_state(self, config):
        raise RuntimeError("intentional state initialization failure")

    def process_item(self, item, state):
        return item


class _CloseAwareItemModule:
    def __init__(self, config=None):
        self.marker_path = (config or {})["marker_path"]

    def process_item(self, item, state):
        return item

    def close(self):
        from pathlib import Path

        Path(self.marker_path).write_text("closed", encoding="utf-8")


def _echo_plugin():
    return PluginSpec(
        plugin_id="sample.echo",
        api_version=PLUGIN_API_VERSION,
        modules=(
            ModuleSpec(
                module_id="echo",
                kind="processor_item",
                factory=_EchoItemModule,
                execution_modes=("thread", "process"),
            ),
        ),
    )


def _echo_config_schema(config):
    if not isinstance(config.get("prefix", ""), str):
        raise ValueError("prefix must be a string")
    return {**config, "normalized": True}


def test_public_plugin_protocols_are_structural():
    assert isinstance(_EchoItemModule(), IItemProcessor)
    assert isinstance(_EchoItemModule(), IStatefulItemProcessor)
    assert isinstance(_EchoBatchModule(), IBatchProcessor)
    assert isinstance(_SequenceSource(), ISource)


def test_plugin_manager_loads_entry_point_manifest():
    registry = PluginRegistry()
    manager = PluginManager(registry)
    manager.load([_EntryPoint("sample-echo", _echo_plugin)])

    assert registry.get_module("sample.echo/echo") is not None
    assert registry.list_modules("processor_item") == ["sample.echo/echo"]


def test_plugin_import_failure_names_entry_point_and_reason():
    manager = PluginManager(PluginRegistry())

    with pytest.raises(PluginError, match="broken-plugin.*dependency is missing"):
        manager.load([_BrokenEntryPoint()])


def test_plugins_with_same_local_module_id_are_namespaced():
    registry = PluginRegistry()
    for plugin_id in ("vendor.one", "vendor.two"):
        registry.register_plugin(
            PluginSpec(
                plugin_id=plugin_id,
                api_version=PLUGIN_API_VERSION,
                modules=(ModuleSpec("detector", "detector", _EchoItemModule),),
            )
        )

    assert registry.get_module("vendor.one/detector") is not None
    assert registry.get_module("vendor.two/detector") is not None
    assert registry.get_module("detector") is None


def test_duplicate_alias_and_api_mismatch_are_reported():
    registry = PluginRegistry()
    registry.register_plugin(
        PluginSpec(
            "vendor.one",
            PLUGIN_API_VERSION,
            (ModuleSpec("first", "detector", _EchoItemModule, legacy_ids=("shared",)),),
        )
    )
    with pytest.raises(PluginError, match="already registered"):
        registry.register_plugin(
            PluginSpec(
                "vendor.two",
                PLUGIN_API_VERSION,
                (ModuleSpec("second", "detector", _EchoItemModule, legacy_ids=("shared",)),),
            )
        )
    with pytest.raises(PluginError, match="API"):
        registry.register_plugin(PluginSpec("vendor.old", PLUGIN_API_VERSION + 1))


def test_duplicate_ids_inside_one_manifest_are_rejected_atomically():
    registry = PluginRegistry()
    manifest = PluginSpec(
        "vendor.duplicate",
        PLUGIN_API_VERSION,
        modules=(
            ModuleSpec("same", "detector", _EchoItemModule),
            ModuleSpec("same", "tracker", _EchoItemModule),
        ),
    )

    with pytest.raises(PluginError, match="Duplicate module id"):
        registry.register_plugin(manifest)

    assert registry.list_modules() == []


def test_batch_processor_kind_is_thread_only():
    registry = PluginRegistry()
    registry.register_plugin(
        PluginSpec(
            "vendor.batch",
            PLUGIN_API_VERSION,
            modules=(ModuleSpec("merge", "batch_processor", _EchoItemModule, ("thread",)),),
        )
    )

    assert registry.get_module("vendor.batch/merge").spec.kind == "batch_processor"
    with pytest.raises(PluginError, match="batch processor.*only supports thread"):
        PluginRegistry().register_plugin(
            PluginSpec(
                "vendor.batch.process",
                PLUGIN_API_VERSION,
                modules=(ModuleSpec("merge", "batch_processor", _EchoItemModule, ("process",)),),
            )
        )


def _register_process_echo_module(plugin_id):
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id,
            PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    "echo",
                    "processor_item",
                    _EchoItemModule,
                    execution_modes=("thread", "process"),
                ),
            ),
        )
    )
    module_id = f"{plugin_id}/echo"
    return ItemModuleAdapter(plugin_registry.get_module(module_id)), module_id


def test_process_item_configuration_must_be_serializable_before_start():
    module, module_id = _register_process_echo_module("test.process-config")
    module.set_params(
        module_id=module_id,
        execution_mode="process",
        config={"prefix": lambda value: value},
    )

    with pytest.raises(PluginError, match="configuration must be serializable"):
        module.init()


def test_process_item_rejects_unserializable_input_without_queueing_it():
    module, module_id = _register_process_echo_module("test.process-input")
    module.set_params(
        module_id=module_id,
        execution_mode="process",
        config={"prefix": ""},
    )
    assert module.init() is True
    sink = _ProcessQueueSink()
    module._mp_control = sink
    module.put({"frame_id": 7})
    assert sink.items[0][0] == "__evileye_plugin_input__"
    assert pickle.loads(sink.items[0][1]) == {"frame_id": 7}

    with pytest.raises(PluginError, match="input item must be serializable"):
        module.put(lambda: None)

    assert module.degraded is True
    assert len(sink.items) == 1
    module._mp_control = None
    module.release()


def test_process_item_serializes_worker_output():
    worker = ItemModuleWorker.__new__(ItemModuleWorker)
    worker.module_id = "test.process-output/echo"
    worker.module = _EchoItemModule({"prefix": "result-"})
    worker.module_state = {"count": 0}
    worker.logger = logging.getLogger("test.plugin-runtime")
    worker._stop_event = threading.Event()

    result = worker.worker_impl(
        ("__evileye_plugin_input__", pickle.dumps("frame"))
    )

    assert result[:2] == ("__evileye_plugin_runtime__", "output")
    assert pickle.loads(result[2]) == "result-frame:1"


def test_process_item_rejects_unserializable_output_in_worker():
    worker = ItemModuleWorker.__new__(ItemModuleWorker)
    worker.module_id = "test.process-output/echo"
    worker.module = _UnpicklableOutputModule()
    worker.module_state = None
    worker.logger = logging.getLogger("test.plugin-runtime")
    worker._stop_event = threading.Event()

    result = worker.worker_impl(
        ("__evileye_plugin_input__", pickle.dumps("frame"))
    )

    assert result[0] == "__evileye_plugin_runtime__"
    assert result[1] == "error"
    assert "process_item result must be serializable" in result[2]
    assert worker._stop_event.is_set()


def test_module_rejects_unsupported_execution_mode_before_init():
    registry = PluginRegistry()
    registry.register_plugin(
        PluginSpec(
            "vendor.thread_only",
            PLUGIN_API_VERSION,
            modules=(ModuleSpec("echo", "processor_item", _EchoItemModule, ("thread",)),),
        )
    )
    module = ItemModuleAdapter(registry.get_module("vendor.thread_only/echo"))

    with pytest.raises(PluginError, match="vendor.thread_only/echo.*execution_mode='process'"):
        module.set_params(module_id="vendor.thread_only/echo", execution_mode="process")


def test_batch_processor_adapter_preserves_batch_semantics_and_state():
    registry = PluginRegistry()
    registry.register_plugin(
        PluginSpec(
            "vendor.batch_adapter",
            PLUGIN_API_VERSION,
            modules=(ModuleSpec("merge", "batch_processor", _EchoBatchModule, ("thread",)),),
        )
    )
    module = BatchProcessorModuleAdapter(registry.get_module("vendor.batch_adapter/merge"))
    module.set_params(
        module_id="vendor.batch_adapter/merge",
        execution_mode="thread",
        config={"prefix": "camera-"},
        source_ids=[1, 2],
    )
    assert module.init() is True
    module.start()

    first = module.process_batch({1: ["a"], 2: ["b", "c"]})
    second = module.process_batch({1: ["d"]})

    assert first == ["camera-1:1:1", "camera-2:2:1"]
    assert second == ["camera-1:1:2"]
    assert module.get_source_ids() == [1, 2]
    assert isinstance(module, IRuntimeStatusProvider)
    assert module.get_runtime_stats() == {
        "module_id": "vendor.batch_adapter/merge",
        "execution_mode": "thread",
        "module_initialized": True,
        "degraded": False,
    }
    module.release()


def test_declared_module_config_schema_validates_and_normalizes():
    registry = PluginRegistry()
    registry.register_plugin(
        PluginSpec(
            "vendor.configured",
            PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    "echo",
                    "processor_item",
                    _EchoItemModule,
                    config_schema=_echo_config_schema,
                ),
            ),
        )
    )

    assert registry.validate_module_config(
        "vendor.configured/echo", {"prefix": "safe-"}
    ) == {"prefix": "safe-", "normalized": True}
    with pytest.raises(PluginError, match="prefix must be a string"):
        registry.validate_module_config("vendor.configured/echo", {"prefix": 2})


def test_invalid_item_config_is_rejected_before_factory_runs():
    factory_calls = []

    def factory(config=None):
        factory_calls.append(config)
        return _EchoItemModule(config)

    def reject_config(config):
        raise ValueError("policy is required")

    plugin_id = "test.schema-before-factory"
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id,
            PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    "probe",
                    "processor_item",
                    factory,
                    execution_modes=("thread",),
                    config_schema=reject_config,
                ),
            ),
        )
    )
    module_id = f"{plugin_id}/probe"
    adapter = EvilEyeBase.create_instance(module_id)

    with pytest.raises(PluginError, match="policy is required"):
        adapter.set_params(module_id=module_id, config={})

    assert factory_calls == []


def test_item_module_adapter_runs_thread_mode_with_per_worker_state():
    module_id = "test.plugin/echo"
    registered = RegisteredModule(
        "test.plugin",
        ModuleSpec("echo", "processor_item", _EchoItemModule, ("thread",)),
    )
    plugin_registry.register_plugin(
        PluginSpec("test.plugin", PLUGIN_API_VERSION, modules=(registered.spec,))
    )
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=module_id,
        execution_mode="thread",
        config={"prefix": "ok-"},
        source_ids=[0],
    )
    adapter.init()
    adapter.start()
    try:
        adapter.put("frame")
        deadline = time.monotonic() + 2.0
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            if result is None:
                time.sleep(0.01)
        assert result == "ok-frame:1"
    finally:
        adapter.stop()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_item_module_worker_failure_is_visible_in_runtime_diagnostics(execution_mode):
    plugin_id = f"test.failure-{execution_mode}"
    spec = ModuleSpec(
        "failure",
        "processor_item",
        _FailingItemModule,
        execution_modes=(execution_mode,),
    )
    registered = RegisteredModule(plugin_id, spec)
    plugin_registry.register_plugin(
        PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=f"{plugin_id}/failure",
        execution_mode=execution_mode,
    )
    adapter.init()
    adapter.start()
    try:
        adapter.put("frame")
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        stats = adapter.get_runtime_stats()
        while not stats["degraded"] and time.monotonic() < deadline:
            time.sleep(0.01)
            stats = adapter.get_runtime_stats()

        assert stats["degraded"] is True
        debug = adapter.insert_debug_info_by_id({})
        assert debug["plugin_runtime"]["degraded"] is True
    finally:
        adapter.stop()


def test_item_module_input_queue_overflow_is_explicit_and_degraded():
    import threading

    class _BlockingModule:
        started = threading.Event()
        release = threading.Event()

        def process_item(self, item, state):
            self.started.set()
            self.release.wait(timeout=2.0)
            return item

    module_id = "test.queue/slow"
    spec = ModuleSpec("slow", "processor_item", _BlockingModule, ("thread",))
    registered = RegisteredModule("test.queue", spec)
    plugin_registry.register_plugin(
        PluginSpec("test.queue", PLUGIN_API_VERSION, modules=(spec,))
    )
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=module_id,
        execution_mode="thread",
        queue_size=1,
    )
    adapter.init()
    adapter.start()
    try:
        adapter.put("processing")
        assert _BlockingModule.started.wait(timeout=2.0)
        adapter.put("queued")
        with pytest.raises(RuntimeError, match="input queue is full"):
            adapter.put("overflow")
        assert adapter.get_runtime_stats()["degraded"] is True
    finally:
        _BlockingModule.release.set()
        adapter.stop()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_item_module_adapter_passes_runtime_context_to_worker(execution_mode):
    assert isinstance(_ContextItemModule(), IContextualStatefulItemProcessor)
    plugin_id = f"test.context-{execution_mode}"
    spec = ModuleSpec(
        "context",
        "processor_item",
        _ContextItemModule,
        execution_modes=(execution_mode,),
    )
    plugin_registry.register_plugin(
        PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    module_id = f"{plugin_id}/context"
    adapter = ItemModuleAdapter(plugin_registry.get_module(module_id))
    adapter.set_params(
        module_id=module_id,
        execution_mode=execution_mode,
        source_ids=[0, 3],
    )
    assert adapter.init() is True
    adapter.start()
    try:
        adapter.put("frame")
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            if result is None:
                time.sleep(0.02)
        assert result == {
            "item": "frame",
            "count": 1,
            "module_id": module_id,
            "execution_mode": execution_mode,
            "source_ids": (0, 3),
        }
    finally:
        adapter.stop()


def test_item_module_adapter_recreates_factory_in_spawn_process():
    module_id = "test.process/echo"
    spec = ModuleSpec(
        "echo",
        "processor_item",
        _EchoItemModule,
        execution_modes=("process",),
    )
    registered = RegisteredModule("test.process", spec)
    plugin_registry.register_plugin(
        PluginSpec("test.process", PLUGIN_API_VERSION, modules=(spec,))
    )
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=module_id,
        execution_mode="process",
        config={"prefix": "spawn-"},
        source_ids=[0],
    )
    adapter.init()
    adapter.start()
    try:
        adapter.put("frame")
        deadline = time.monotonic() + 15.0
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            if result is None:
                time.sleep(0.02)
        assert result == "spawn-frame:1"
    finally:
        adapter.stop()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_item_module_worker_closes_resources_on_stop(tmp_path, execution_mode):
    plugin_id = f"test.close-{execution_mode}"
    spec = ModuleSpec(
        "close-aware",
        "processor_item",
        _CloseAwareItemModule,
        execution_modes=(execution_mode,),
    )
    registered = RegisteredModule(plugin_id, spec)
    plugin_registry.register_plugin(
        PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    marker_path = tmp_path / f"{execution_mode}.closed"
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=registered.qualified_id,
        execution_mode=execution_mode,
        config={"marker_path": str(marker_path)},
    )
    adapter.init()
    adapter.start()
    try:
        adapter.put("item")
        deadline = time.monotonic() + (45.0 if execution_mode == "process" else 2.0)
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            if result is None:
                time.sleep(0.02)
        assert result == "item"
    finally:
        adapter.stop()

    assert marker_path.read_text(encoding="utf-8") == "closed"


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_source_module_adapter_supports_open_read_close(execution_mode):
    module_id = f"test.source-{execution_mode}/sequence"
    spec = ModuleSpec(
        "sequence",
        "source",
        _SequenceSource,
        execution_modes=(execution_mode,),
    )
    registered = RegisteredModule(f"test.source-{execution_mode}", spec)
    plugin_registry.register_plugin(
        PluginSpec(registered.plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=module_id,
        execution_mode=execution_mode,
        source_ids=[4],
        config={"items": [{"source_id": 4, "frame_id": 1}, {"source_id": 4, "frame_id": 2}]},
    )
    source.init()
    source.start()
    try:
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        items = []
        while len(items) < 2 and time.monotonic() < deadline:
            items.extend(source.get())
            if len(items) < 2:
                time.sleep(0.02)
        assert [item["frame_id"] for item in items] == [1, 2]
    finally:
        source.stop()


def test_process_source_failure_is_visible_when_output_queue_is_full():
    module_id = "test.source-failure/sequence"
    spec = ModuleSpec("sequence", "source", _FailingSource, ("process",))
    registered = RegisteredModule("test.source-failure", spec)
    plugin_registry.register_plugin(
        PluginSpec("test.source-failure", PLUGIN_API_VERSION, modules=(spec,))
    )
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=module_id,
        execution_mode="process",
        queue_size=1,
        source_ids=[5],
    )
    source.init()
    source.start()
    try:
        deadline = time.monotonic() + 10.0
        while source.is_running() and time.monotonic() < deadline:
            time.sleep(0.02)

        assert source.is_running() is False
        items = source.get()
        assert items == [{"frame_id": 1}]
        assert source.get_runtime_stats()["degraded"] is True
    finally:
        source.stop()


def test_finished_plugin_source_is_not_restarted_on_next_pipeline_tick():
    class _FinishedSource:
        starts = 0

        def is_running(self):
            return False

        def is_finished(self):
            return True

        def start(self):
            self.starts += 1

    source = _FinishedSource()
    processor = ProcessorSource.__new__(ProcessorSource)
    processor.processors = [source]

    processor.run_sources()

    assert source.starts == 0


def test_builtin_capture_sources_use_spi_adapter_and_keep_capture_backend(monkeypatch):
    # Importing the builtins registers their public SPI manifests.
    from evileye.capture.video_capture_opencv import VideoCaptureOpencv
    from evileye.capture.video_capture_gstreamer import VideoCaptureGStreamer

    for source_type in (VideoCaptureOpencv, VideoCaptureGStreamer):
        registered = plugin_registry.get_module(source_type.__name__)
        assert registered is not None
        assert "legacy_source_protocol" in registered.spec.capabilities
        assert isinstance(EvilEyeBase.create_instance(source_type.__name__), SourceModuleAdapter)

    generated = []

    def fake_init(source):
        source.is_inited = True
        return True

    def fake_start(source):
        source.run_flag = True

    def fake_get(source):
        if not generated:
            generated.append(True)
            source._test_finished = True
            return [{"source_id": 3, "frame_id": 9}]
        return []

    def fake_is_finished(source):
        return bool(getattr(source, "_test_finished", False))

    monkeypatch.setattr(VideoCaptureOpencv, "init", fake_init)
    monkeypatch.setattr(VideoCaptureOpencv, "start", fake_start)
    monkeypatch.setattr(VideoCaptureOpencv, "get", fake_get)
    monkeypatch.setattr(VideoCaptureOpencv, "is_finished", fake_is_finished)
    monkeypatch.setattr(VideoCaptureOpencv, "stop", lambda source: setattr(source, "run_flag", False))

    adapter = EvilEyeBase.create_instance("VideoCaptureOpencv")
    adapter.set_params(
        type="VideoCaptureOpencv",
        execution_mode="process",
        source="VideoFile",
        camera="unused.mp4",
        source_ids=[3],
        source_names=["Test camera"],
    )
    assert adapter.init() is True
    assert adapter.execution_mode == "thread"
    assert adapter.get_runtime_stats()["backend_execution_mode"] == "process"
    assert adapter._module.execution_mode == "process"
    assert adapter.source_ids == [3]
    assert adapter.source_names == ["Test camera"]

    adapter.start()
    try:
        deadline = time.monotonic() + 2.0
        frames = []
        while not frames and time.monotonic() < deadline:
            frames.extend(adapter.get())
            if not frames:
                time.sleep(0.01)
        assert frames == [{"source_id": 3, "frame_id": 9}]
    finally:
        adapter.stop()


def test_builtin_model_tracker_and_attribute_modules_use_spi_adapter():
    import evileye.attributes_detection as attributes
    import evileye.object_detector as detectors
    import evileye.object_tracker as trackers
    from evileye.object_detector import object_detection_rfdetr

    builtins = (
        detectors.ObjectDetectorYolo,
        detectors.ObjectDetectorRtdetr,
        detectors.ObjectDetectorRfdetr,
        detectors.ObjectDetectorYoloMp,
        attributes.AttributeDetector,
        attributes.AttributeClassifier,
        trackers.ObjectTrackingBotsort,
    )
    for module_class in builtins:
        registered = plugin_registry.get_module(module_class.__name__)
        if (
            module_class is detectors.ObjectDetectorRfdetr
            and not object_detection_rfdetr._SUPPORT_RFDETR
        ):
            assert registered is None
            continue
        assert registered is not None
        adapter = EvilEyeBase.create_instance(module_class.__name__)
        if module_class in {trackers.ObjectTrackingBotsort, attributes.AttributeClassifier}:
            assert registered.spec.kind == "processor_item"
            assert "legacy_processor_protocol" not in registered.spec.capabilities
            assert isinstance(adapter, ItemModuleAdapter)
        else:
            assert "legacy_processor_protocol" in registered.spec.capabilities
            assert isinstance(adapter, LegacyProcessorModuleAdapter)
        assert adapter.ResultType is module_class.ResultType


def test_legacy_processor_adapter_preserves_queue_lifecycle():
    class _LegacyQueueProcessor(EvilEyeBase):
        ResultType = dict

        def __init__(self):
            super().__init__()
            self.items = []

        def set_params_impl(self):
            self.source_ids = self.params.get("source_ids", [])

        def get_params_impl(self):
            return dict(self.params)

        def init_impl(self, **kwargs):
            self.init_kwargs = kwargs
            return True

        def get_source_ids(self):
            return self.source_ids

        def put(self, item):
            self.items.append(item)

        def get(self):
            return self.items.pop(0) if self.items else None

        def start(self):
            self.started = True

        def stop(self):
            self.stopped = True

        def release_impl(self):
            return None

        def reset_impl(self):
            self.items.clear()

        def default(self):
            self.items.clear()

    registry = PluginRegistry()
    spec = ModuleSpec(
        "queue-processor",
        "detector",
        _LegacyQueueProcessor,
        ("thread",),
        capabilities=("legacy_processor_protocol",),
    )
    registry.register_plugin(PluginSpec("sample.legacy", PLUGIN_API_VERSION, (spec,)))
    registered = registry.get_module("sample.legacy/queue-processor")
    adapter = LegacyProcessorModuleAdapter(registered)
    adapter.set_params(module_id="sample.legacy/queue-processor", source_ids=[7])

    assert adapter.init(dependency="passed") is True
    adapter.start()
    adapter.put({"frame_id": 5})
    assert adapter.get() == {"frame_id": 5}
    assert adapter.get_source_ids() == [7]
    assert adapter._module.init_kwargs == {"dependency": "passed"}
    assert adapter._module.started is True
    adapter.stop()
    assert adapter._module.stopped is True


class _FakeBackendProcess:
    def __init__(self, exitcode, alive=False):
        self.exitcode = exitcode
        self._alive = alive

    def is_alive(self):
        return self._alive


def _source_adapter_for_exit_check():
    adapter = SourceModuleAdapter.__new__(SourceModuleAdapter)
    adapter.module_id = "test/source"
    adapter.degraded = False
    adapter._backend_worker_exitcodes = []
    adapter.logger = logging.getLogger("test.source_adapter")
    return adapter


def test_legacy_source_expected_termination_does_not_mark_runtime_degraded():
    from types import SimpleNamespace

    adapter = _source_adapter_for_exit_check()
    module = SimpleNamespace(
        _mp_control=SimpleNamespace(
            processes=[_FakeBackendProcess(-15)],
            no_restart_exit_codes={-15},
        )
    )

    adapter._capture_legacy_worker_exitcodes(module)

    assert adapter.degraded is False
    assert adapter._backend_worker_exitcodes == [-15]


def test_legacy_source_unexpected_worker_exit_marks_runtime_degraded():
    from types import SimpleNamespace

    adapter = _source_adapter_for_exit_check()
    module = SimpleNamespace(
        _mp_control=SimpleNamespace(
            processes=[_FakeBackendProcess(-9)],
            no_restart_exit_codes={-15},
        )
    )

    adapter._capture_legacy_worker_exitcodes(module)

    assert adapter.degraded is True
    assert adapter._backend_worker_exitcodes == [-9]


def test_legacy_source_worker_alive_after_stop_marks_runtime_degraded():
    from types import SimpleNamespace

    adapter = _source_adapter_for_exit_check()
    module = SimpleNamespace(
        _mp_control=SimpleNamespace(
            processes=[_FakeBackendProcess(None, alive=True)],
            no_restart_exit_codes={-15},
        )
    )

    adapter._capture_legacy_worker_exitcodes(module)

    assert adapter.degraded is True
    assert adapter._backend_worker_exitcodes == [None]


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_item_module_state_initialization_failure_is_visible(execution_mode):
    plugin_id = f"test.init-failure-{execution_mode}"
    spec = ModuleSpec(
        "failure",
        "processor_item",
        _FailingStateItemModule,
        execution_modes=(execution_mode,),
    )
    registered = RegisteredModule(plugin_id, spec)
    plugin_registry.register_plugin(
        PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=registered.qualified_id,
        execution_mode=execution_mode,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        while time.monotonic() < deadline:
            adapter.get()
            if adapter.get_runtime_stats()["degraded"]:
                break
            time.sleep(0.02)
        assert adapter.get_runtime_stats()["degraded"] is True
    finally:
        adapter.stop()



def test_process_source_rejects_unserializable_config_before_start():
    spec = ModuleSpec(
        "sequence",
        "source",
        _SequenceSource,
        execution_modes=("process",),
    )
    registered = RegisteredModule("test.source-config", spec)
    plugin_registry.register_plugin(
        PluginSpec(registered.plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=registered.qualified_id,
        execution_mode="process",
        config={"callback": lambda: None},
    )

    with pytest.raises(PluginError, match="source configuration.*serializable"):
        source.init()


def test_process_source_reports_unserializable_items():
    spec = ModuleSpec(
        "unserializable",
        "source",
        _UnpicklableOutputSource,
        execution_modes=("process",),
    )
    registered = RegisteredModule("test.source-output", spec)
    plugin_registry.register_plugin(
        PluginSpec(registered.plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=registered.qualified_id,
        execution_mode="process",
    )
    assert source.init() is True
    source.start()
    try:
        deadline = time.monotonic() + 15.0
        while time.monotonic() < deadline and not source.degraded:
            source.get()
            time.sleep(0.02)
        assert source.degraded is True
        assert source.is_finished() is True
    finally:
        source.stop()


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_item_module_publishes_late_model_class_mapping(execution_mode):
    module_id = f"test.mapping-{execution_mode}/detector"
    spec = ModuleSpec(
        "detector",
        "processor_item",
        _LateModelMappingItemModule,
        execution_modes=(execution_mode,),
        capabilities=("model_class_mapping",),
    )
    registered = RegisteredModule(f"test.mapping-{execution_mode}", spec)
    plugin_registry.register_plugin(
        PluginSpec(registered.plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    assert isinstance(_LateModelMappingItemModule(), IModelClassMappingProvider)
    adapter = ItemModuleAdapter(registered)
    adapter.set_params(
        module_id=module_id,
        execution_mode=execution_mode,
        config={"model_class_mapping": {"person": 0, "helmet": 1}},
    )
    assert adapter.reports_model_class_mapping is True
    assert adapter.init() is True
    adapter.start()
    try:
        adapter.put("frame")
        deadline = time.monotonic() + (15.0 if execution_mode == "process" else 2.0)
        result = None
        while result is None and time.monotonic() < deadline:
            result = adapter.get()
            if result is None:
                time.sleep(0.02)
        assert result == "frame"
        assert adapter.get_model_class_mapping() == {"person": 0, "helmet": 1}
        assert adapter.get_runtime_stats()["degraded"] is False
    finally:
        adapter.stop()


def test_item_module_uses_declared_default_execution_mode():
    registry = PluginRegistry()
    spec = ModuleSpec(
        "worker",
        "processor_item",
        _EchoItemModule,
        execution_modes=("thread", "process"),
        default_execution_mode="process",
    )
    registry.register_plugin(
        PluginSpec("test.mode-default", PLUGIN_API_VERSION, modules=(spec,))
    )

    adapter = ItemModuleAdapter(registry.get_module("test.mode-default/worker"))
    adapter.set_params(module_id="test.mode-default/worker")

    assert adapter.execution_mode == "process"


def test_registry_rejects_unsupported_default_execution_mode():
    registry = PluginRegistry()
    spec = ModuleSpec(
        "worker",
        "processor_item",
        _EchoItemModule,
        execution_modes=("thread",),
        default_execution_mode="process",
    )

    with pytest.raises(PluginError, match="default execution mode 'process' is not supported"):
        registry.register_plugin(
            PluginSpec("test.invalid-mode-default", PLUGIN_API_VERSION, modules=(spec,))
        )
