import json
from pathlib import Path

from evileye.pipelines.pipeline_surveillance import PipelineSurveillance
import pytest


def test_pipeline_normalizes_ipc_mode_without_forcing_execution_mode():
    pipeline = PipelineSurveillance()
    src = {
        "pipeline_class": "PipelineSurveillance",
        "ipc_mode": "descriptor",
        "sources": [{"source_ids": [0]}],
        "detectors": [{"source_ids": [0], "execution_mode": "process"}],
        "trackers": [{"source_ids": [0]}],
    }

    normalized = pipeline._normalize_pipeline_params(src)

    assert normalized["ipc_mode"] == "descriptor"
    assert "execution_mode" not in normalized["sources"][0]
    assert normalized["sources"][0]["ipc_mode"] == "descriptor"
    assert normalized["detectors"][0]["execution_mode"] == "process"
    assert normalized["detectors"][0]["ipc_mode"] == "descriptor"
    assert "execution_mode" not in normalized["trackers"][0]


def test_pipeline_ipc_mode_defaults_to_standard():
    pipeline = PipelineSurveillance()
    src = {
        "pipeline_class": "PipelineSurveillance",
        "sources": [{"source_ids": [0]}],
    }
    normalized = pipeline._normalize_pipeline_params(src)
    assert normalized["ipc_mode"] == "standard"
    assert normalized["sources"][0]["ipc_mode"] == "standard"


def test_real_configs_execution_mode_policy():
    repo_root = Path(__file__).resolve().parents[3]
    single_sp = json.loads(
        (repo_root / "configs" / "single_video_singleprocess.json").read_text()
    )
    poly = json.loads((repo_root / "configs" / "poly-videos-gst.json").read_text())

    assert single_sp["pipeline"]["sources"][0]["execution_mode"] == "thread"
    assert single_sp["pipeline"]["detectors"][0]["execution_mode"] == "thread"

    assert poly["pipeline"]["sources"][0]["execution_mode"] == "process"
    assert poly["pipeline"]["detectors"][0]["execution_mode"] == "process"
    assert "execution_mode" not in poly["pipeline"]["trackers"][0]


def test_deploy_samples_pin_thread_execution_mode():
    repo_root = Path(__file__).resolve().parents[3]
    sample = json.loads(
        (repo_root / "evileye" / "samples_configs" / "single_video.json").read_text()
    )
    for key in ("sources", "detectors", "trackers"):
        assert sample["pipeline"][key][0]["execution_mode"] == "thread"


def test_module_groups_extend_and_replace_legacy_sections():
    pipeline = PipelineSurveillance()
    base = {"detectors": [{"type": "BuiltinDetector"}]}
    extended = pipeline._normalize_pipeline_params(
        {
            **base,
            "modules": {
                "detectors": {
                    "mode": "extend",
                    "items": [{"module_id": "vendor/custom-detector"}],
                }
            },
        }
    )
    assert extended["detectors"] == [
        {"type": "BuiltinDetector", "ipc_mode": "standard"},
        {"module_id": "vendor/custom-detector", "ipc_mode": "standard"},
    ]

    replaced = pipeline._normalize_pipeline_params(
        {
            **base,
            "modules": {
                "detectors": {
                    "mode": "replace",
                    "items": [{"module_id": "vendor/replacement"}],
                }
            },
        }
    )
    assert [item.get("module_id") for item in replaced["detectors"]] == [
        "vendor/replacement"
    ]


def test_module_group_requires_explicit_mode_and_list():
    pipeline = PipelineSurveillance()
    with pytest.raises(ValueError, match="mode"):
        pipeline._normalize_pipeline_params(
            {"modules": {"detectors": {"items": []}}}
        )


def test_preprocessor_group_can_mix_item_plugins_and_lifecycle_modules():
    from evileye.core.base_class import EvilEyeBase
    from evileye.core.plugins import PLUGIN_API_VERSION, ModuleSpec, PluginSpec, plugin_registry
    from evileye.core.plugin_runtime import ItemModuleAdapter

    class _ItemPreprocessor:
        def process_item(self, item, state):
            return item

    class _LifecyclePreprocessor(EvilEyeBase):
        def __init__(self):
            super().__init__()

        def put(self, item):
            pass

        def get(self):
            return None

        def get_source_ids(self):
            return None

        def set_params_impl(self):
            pass

        def get_params_impl(self):
            return {}

        def init_impl(self, **kwargs):
            return True

        def reset_impl(self):
            pass

        def release_impl(self):
            pass

        def default(self):
            pass

    item_spec = ModuleSpec("item", "processor_item", _ItemPreprocessor, ("thread",))
    lifecycle_spec = ModuleSpec("lifecycle", "preprocessor", _LifecyclePreprocessor)
    plugin_registry.register_plugin(
        PluginSpec("test.mixed-item", PLUGIN_API_VERSION, modules=(item_spec,))
    )
    plugin_registry.register_plugin(
        PluginSpec("test.mixed-lifecycle", PLUGIN_API_VERSION, modules=(lifecycle_spec,))
    )

    pipeline = PipelineSurveillance()
    pipeline._init_preprocessors(
        [
            {"module_id": "test.mixed-item/item"},
            {"module_id": "test.mixed-lifecycle/lifecycle"},
        ]
    )

    processors = pipeline.processors[0].get_processors()
    assert isinstance(processors[0], ItemModuleAdapter)
    assert isinstance(processors[1], _LifecyclePreprocessor)
