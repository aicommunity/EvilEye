from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from evileye.core.contracts import PipelineConfig, PipelineDependencies
from evileye.core.interfaces import IPipeline


PLUGIN_FILE = (
    Path(__file__).resolve().parents[3]
    / "examples"
    / "plugin_package"
    / "evileye_example_plugin.py"
)


def _load_example_plugin_module():
    spec = spec_from_file_location("evileye_example_plugin_contract_test", PLUGIN_FILE)
    assert spec is not None and spec.loader is not None
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_example_plugin_exposes_pipeline_spec_and_complete_lifecycle():
    plugin = _load_example_plugin_module().load_plugin()
    assert plugin.plugin_id == "example"
    assert [pipeline.pipeline_id for pipeline in plugin.pipelines] == [
        "marker-pipeline"
    ]

    dependencies = PipelineDependencies(
        config=PipelineConfig(raw_config={"factory_marker": "from-dependencies"})
    )
    pipeline = plugin.pipelines[0].factory(dependencies)
    assert isinstance(pipeline, IPipeline)
    assert pipeline.marker == "from-dependencies"

    pipeline.set_params(marker="unit-test")
    assert pipeline.init() is True
    pipeline.start()
    assert pipeline.process() == {"marker": "unit-test", "sequence": 1}
    assert pipeline.get_current_results() == {
        "marker": "unit-test",
        "sequence": 1,
    }
    assert pipeline.get_results_list() == [
        {"marker": "unit-test", "sequence": 1}
    ]
    pipeline.stop()
    pipeline.release()

    assert pipeline.running is False
    assert pipeline.is_inited is False
