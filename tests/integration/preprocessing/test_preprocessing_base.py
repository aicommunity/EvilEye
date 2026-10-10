"""Integration coverage for the built-in preprocessing plugin."""

import evileye.preprocessing  # noqa: F401

from evileye.core.base_class import EvilEyeBase
from evileye.core.plugins import plugin_registry
from evileye.preprocessing.preprocessing_base import PreprocessingBase
from evileye.preprocessing.preprocessing_pipeline import PreprocessingPipeline


def test_preprocessing_base_uses_component_lifecycle():
    assert issubclass(PreprocessingBase, EvilEyeBase)


def test_preprocessing_pipeline_is_registered_in_plugin_spi():
    registered = plugin_registry.get_module("PreprocessingPipeline")
    assert registered is not None
    assert registered.spec.factory is PreprocessingPipeline
    assert registered.spec.kind == "processor_item"
