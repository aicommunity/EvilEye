"""Regression checks for import order and shared component discovery."""

import evileye.preprocessing  # noqa: F401

from evileye.core.plugins import plugin_registry


def test_preprocessing_import_registers_builtin_module():
    registered = plugin_registry.get_module("PreprocessingPipeline")
    assert registered is not None
    assert registered.spec.kind == "processor_item"


def test_preprocessing_is_visible_by_qualified_and_legacy_id():
    assert plugin_registry.get_module("PreprocessingPipeline") is not None
    assert plugin_registry.get_module("evileye/PreprocessingPipeline") is not None
