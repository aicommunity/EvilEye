from __future__ import annotations

import time

import pytest

from evileye.core.base_class import EvilEyeBase
from evileye.core.plugin_runtime import ParallelItemModuleAdapter
from evileye.core.plugins import (
    ModuleSpec,
    PLUGIN_API_VERSION,
    PluginSpec,
    plugin_registry,
)


class _OrderedEchoModule:
    def process_item(self, item, state):
        delay, value = item
        time.sleep(delay)
        return value


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_parallel_item_runtime_preserves_input_order(execution_mode):
    plugin_id = "test_parallel_item_runtime"
    if plugin_registry.get_module(f"{plugin_id}/echo") is None:
        plugin_registry.register_plugin(
            PluginSpec(
                plugin_id=plugin_id,
                api_version=PLUGIN_API_VERSION,
                modules=(
                    ModuleSpec(
                        module_id="echo",
                        kind="processor_item",
                        factory=_OrderedEchoModule,
                        execution_modes=("thread", "process"),
                        capabilities=("parallel_items",),
                    ),
                ),
            )
        )

    adapter = EvilEyeBase.create_instance(f"{plugin_id}/echo")
    assert isinstance(adapter, ParallelItemModuleAdapter)
    adapter.set_params(
        module_id=f"{plugin_id}/echo",
        execution_mode=execution_mode,
        worker_count=2,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        adapter.put((0.2, "first"))
        adapter.put((0.0, "second"))
        deadline = time.monotonic() + 15
        outputs = []
        while len(outputs) < 2 and time.monotonic() < deadline:
            result = adapter.get()
            if result is not None:
                outputs.append(result)
            else:
                time.sleep(0.01)
        assert outputs == ["first", "second"]
    finally:
        adapter.stop()
        adapter.release()


class _FailingInitializationModule:
    def create_state(self, config, context=None):
        raise RuntimeError("intentional parallel init failure")

    def process_item(self, item, state):
        return item


def _register_failing_initialization_module():
    plugin_id = "test_parallel_item_runtime_init_failure"
    if plugin_registry.get_module(f"{plugin_id}/failure") is None:
        plugin_registry.register_plugin(
            PluginSpec(
                plugin_id=plugin_id,
                api_version=PLUGIN_API_VERSION,
                modules=(
                    ModuleSpec(
                        module_id="failure",
                        kind="processor_item",
                        factory=_FailingInitializationModule,
                        execution_modes=("thread", "process"),
                        capabilities=("parallel_items",),
                    ),
                ),
            )
        )
    return f"{plugin_id}/failure"


def test_parallel_item_runtime_reports_worker_initialization_failure():
    adapter = EvilEyeBase.create_instance(_register_failing_initialization_module())
    adapter.set_params(
        execution_mode="thread",
        worker_count=2,
    )
    assert adapter.init() is True
    adapter.start()
    try:
        deadline = time.monotonic() + 10
        while not adapter.degraded and time.monotonic() < deadline:
            adapter.get()
            time.sleep(0.01)
        assert adapter.degraded is True
        assert adapter.get() is None
    finally:
        adapter.stop()
        adapter.release()
