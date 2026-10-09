import pytest

from evileye.controller.services.pipeline_service import PipelineService
from evileye.core.plugins import PLUGIN_API_VERSION, PipelineSpec, PluginSpec, plugin_registry
from evileye.pipelines import PipelineCapture, PipelineDeclarative, PipelineSurveillance


def test_builtin_pipelines_are_registered_and_created_through_service():
    service = PipelineService()

    assert {"PipelineCapture", "PipelineDeclarative", "PipelineSurveillance"}.issubset(
        set(service.get_available_pipeline_classes())
    )
    assert isinstance(service.create_pipeline("PipelineCapture"), PipelineCapture)
    assert isinstance(service.create_pipeline("PipelineDeclarative"), PipelineDeclarative)
    assert isinstance(service.create_pipeline("PipelineSurveillance"), PipelineSurveillance)


def test_unknown_pipeline_fails_instead_of_falling_back():
    service = PipelineService()

    with pytest.raises(ValueError, match="not found"):
        service.create_pipeline("does-not-exist")


def _custom_pipeline_factory(dependencies):
    assert dependencies.config.raw_config["test_marker"] == "loaded"
    return PipelineCapture()


def test_custom_pipeline_entry_point_factory_receives_runtime_dependencies():
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id="unit.custom_pipeline",
            api_version=PLUGIN_API_VERSION,
            pipelines=(
                PipelineSpec("capture-wrapper", _custom_pipeline_factory),
            ),
        )
    )

    pipeline = PipelineService().create_pipeline(
        "unit.custom_pipeline/capture-wrapper",
        pipeline_params={"test_marker": "loaded"},
        credentials={"camera": "test"},
    )

    assert isinstance(pipeline, PipelineCapture)
