from evileye.core.processor_step import ProcessorStep
from evileye.core.frame import Frame
from evileye.core.base_class import EvilEyeBase


@EvilEyeBase.register("_FanoutDetectorA", kind="detector")
class _FanoutDetectorA(EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.received = []

    def get_source_ids(self):
        return [0]

    def put(self, item):
        self.received.append(item)

    def get(self):
        return None

    def init_impl(self, **kwargs):
        return True

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}

    def default(self):
        pass

    def release_impl(self):
        pass

    def reset_impl(self):
        pass


@EvilEyeBase.register("_FanoutDetectorB", kind="detector")
class _FanoutDetectorB(_FanoutDetectorA):
    pass


class _Proc:
    def __init__(self, requires_materialized_frame=True):
        self.requires_materialized_frame = requires_materialized_frame


def test_adapter_keeps_standard_payload_when_image_exists():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.image = "img"
    data = {"x": 1}
    proc = _Proc(requires_materialized_frame=True)
    adapted = step._adapt_input_for_processor([data, frame], proc)
    assert adapted[0] == data
    assert adapted[1] is frame
    assert adapted[1].image == "img"


def test_adapter_skips_materialization_when_not_required():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.frame_handle = object()
    data = {"x": 1}
    proc = _Proc(requires_materialized_frame=False)
    adapted = step._adapt_input_for_processor([data, frame], proc)
    assert adapted[0] == data
    assert adapted[1] is frame


def test_adapter_keeps_plain_frame_payload():
    step = ProcessorStep.__new__(ProcessorStep)
    frame = Frame()
    frame.image = "img"
    proc = _Proc(requires_materialized_frame=True)
    adapted = step._adapt_input_for_processor(frame, proc)
    assert adapted is frame


def test_processor_step_fans_out_to_all_matching_detectors(monkeypatch):
    monkeypatch.delenv("EVILEYE_PIPELINE_SYNC_MP", raising=False)
    step = ProcessorStep(
        processor_name="detectors",
        class_name="_FanoutDetectorA",
        num_processors=2,
        order=0,
        class_names=["_FanoutDetectorA", "_FanoutDetectorB"],
    )
    frame = Frame()
    frame.source_id = 0
    step.process([[{"detections": []}, frame]])

    assert len(step.processors[0].received) == 1
    assert len(step.processors[1].received) == 1


def test_detector_fanout_merges_detection_lists_per_frame():
    from evileye.object_detector.object_detection_base import DetectionResultList

    frame = Frame()
    frame.source_id = 2
    frame.frame_id = 17
    first = DetectionResultList()
    first.detections = ["person"]
    second = DetectionResultList()
    second.detections = ["helmet"]

    merged = ProcessorStep._merge_detector_fanout([[first, frame], [second, frame]])

    assert len(merged) == 1
    assert merged[0][0].detections == ["person", "helmet"]
    # The input processor result is not mutated during fanout aggregation.
    assert first.detections == ["person"]


def test_generic_detector_plugin_can_skip_an_unassigned_source():
    from evileye.core.plugins import PLUGIN_API_VERSION, ModuleSpec, PluginSpec, plugin_registry
    from evileye.object_detector.object_detection_base import DetectionResultList

    class _ItemModule:
        def process_item(self, item, state):
            return item

    spec = ModuleSpec(
        "noop",
        "processor_item",
        _ItemModule,
        execution_modes=("thread",),
    )
    plugin_registry.register_plugin(
        PluginSpec("test.pipeline-step", PLUGIN_API_VERSION, modules=(spec,))
    )
    module_id = "test.pipeline-step/noop"
    step = ProcessorStep(
        processor_name="detectors",
        class_name=module_id,
        num_processors=1,
        order=0,
    )
    step.set_params([{"module_id": module_id, "source_ids": [1]}])
    step.init()

    frame = Frame()
    frame.source_id = 0
    frame.frame_id = 23
    result = step.process([[{"detections": []}, frame]])

    assert len(result) == 1
    assert isinstance(result[0][0], DetectionResultList)
    assert result[0][0].source_id == 0
    assert result[0][0].frame_id == 23


def test_module_kind_mismatch_fails_before_pipeline_start():
    import pytest

    from evileye.core.plugins import (
        PLUGIN_API_VERSION,
        ModuleSpec,
        PluginError,
        PluginSpec,
        plugin_registry,
    )

    class _SourceModule:
        def open(self):
            pass

        def read(self):
            return None

        def close(self):
            pass

    module_id = "test.stage-validation/source"
    spec = ModuleSpec("source", "source", _SourceModule)
    plugin_registry.register_plugin(
        PluginSpec("test.stage-validation", PLUGIN_API_VERSION, modules=(spec,))
    )
    step = ProcessorStep(
        processor_name="detectors",
        class_name=module_id,
        num_processors=1,
        order=0,
    )

    with pytest.raises(PluginError, match="kind 'source'.*group 'detectors'"):
        step.set_params([{"module_id": module_id, "source_ids": [0]}])
