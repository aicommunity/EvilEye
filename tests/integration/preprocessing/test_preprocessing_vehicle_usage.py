"""Integration checks for preprocessing pipeline construction."""

import evileye.preprocessing  # noqa: F401

from evileye.core.base_class import EvilEyeBase
from evileye.core.plugins import plugin_registry
from evileye.core.processor_frame import ProcessorFrame


def test_preprocessing_pipeline_resolves_through_shared_spi():
    module = plugin_registry.get_module("evileye/PreprocessingPipeline")
    assert module is not None
    instance = EvilEyeBase.create_instance("PreprocessingPipeline")
    instance.set_params(source_ids=[0])
    assert instance.get_params() is not None


def test_processor_frame_instantiates_registered_preprocessor():
    processor = ProcessorFrame(
        processor_name="preprocessors",
        class_name="PreprocessingPipeline",
        num_processors=1,
        order=1,
    )
    assert processor.init() is True
    assert len(processor.processors) == 1
