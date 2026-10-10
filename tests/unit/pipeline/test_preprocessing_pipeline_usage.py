"""Regression checks for built-in preprocessing plugin registration."""

import evileye.preprocessing  # noqa: F401 - registers built-in module

from evileye.core.base_class import EvilEyeBase
from evileye.core.plugins import plugin_registry


def test_preprocessing_pipeline_creation():
    registered = plugin_registry.get_module("PreprocessingPipeline")
    assert registered is not None
    assert registered.spec.kind == "processor_item"

    instance = EvilEyeBase.create_instance("PreprocessingPipeline")
    assert instance is not None
    instance.default()
    instance.set_params(source_ids=[0])
    assert instance.get_params() is not None


def test_processor_frame_with_preprocessing():
    from evileye.core.processor_frame import ProcessorFrame

    processor = ProcessorFrame(
        processor_name="preprocessors",
        class_name="PreprocessingPipeline",
        num_processors=1,
        order=1,
    )
    assert processor.init() is True
    assert len(processor.processors) == 1


def test_preprocessing_available_from_shared_registry():
    assert plugin_registry.get_module("evileye/PreprocessingPipeline") is not None
