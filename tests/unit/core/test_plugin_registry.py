from __future__ import annotations

import time

import pytest

from evileye.core.plugin_runtime import ItemModuleAdapter, SourceModuleAdapter
from evileye.core.processor_source import ProcessorSource
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


class _FailingItemModule:
    def process_item(self, item, state):
        raise RuntimeError("intentional test failure")


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
