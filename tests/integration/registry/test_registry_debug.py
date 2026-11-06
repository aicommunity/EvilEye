"""Integration checks for built-in module discovery through PluginRegistry."""

import evileye.preprocessing  # noqa: F401 - registers built-in module

from evileye.core.plugins import plugin_registry


def test_registry_debug():
    registered = plugin_registry.get_module("PreprocessingPipeline")
    assert registered is not None
    assert registered.spec.kind == "processor_item"


def test_import_evileye_preprocessing():
    assert plugin_registry.get_module("evileye/PreprocessingPipeline") is not None
