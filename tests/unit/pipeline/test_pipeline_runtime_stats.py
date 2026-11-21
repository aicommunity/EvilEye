from types import SimpleNamespace

from evileye.core.pipeline_processors import PipelineProcessors


class _StatsModule:
    def __init__(self, degraded: bool):
        self.degraded = degraded
        self.module_id = "evileye/ObjectDetectorYolo"

    def get_runtime_stats(self):
        return {"degraded": self.degraded, "worker_running": True}


def test_runtime_stats_keep_legacy_keys_and_publish_unique_module_instances():
    stage = SimpleNamespace(
        processors=[_StatsModule(False), _StatsModule(True)],
        params=[
            {"module_id": "evileye/ObjectDetectorYolo"},
            {"module_id": "evileye/ObjectDetectorYolo"},
        ],
        _class_names=["evileye/ObjectDetectorYolo"] * 2,
        _detector_fanout_pending=None,
    )
    stage.get_name = lambda: "detectors"
    pipeline = PipelineProcessors()
    pipeline.processors = [stage]

    runtime = pipeline.get_runtime_stats()

    assert set(runtime["module_instances"]) == {
        "detectors:0:evileye/ObjectDetectorYolo",
        "detectors:1:evileye/ObjectDetectorYolo",
    }
    assert runtime["module_instances"]["detectors:0:evileye/ObjectDetectorYolo"]["degraded"] is False
    assert runtime["module_instances"]["detectors:1:evileye/ObjectDetectorYolo"]["degraded"] is True
    assert "detectors/evileye/ObjectDetectorYolo" in runtime["modules"]
