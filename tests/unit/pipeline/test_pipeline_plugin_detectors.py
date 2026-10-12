import time
import uuid

import pytest

from evileye.core.frame import Frame
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginSpec,
    plugin_registry,
)
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


class _NamedDetector:
    def __init__(self, config=None):
        self.name = (config or {}).get("name", "unnamed")
        self.delay_sec = float((config or {}).get("delay_sec", 0))
        self.return_none = bool((config or {}).get("return_none", False))

    def process_item(self, item, state):
        if self.delay_sec:
            time.sleep(self.delay_sec)
        frame = item[-1] if isinstance(item, (list, tuple)) else item
        if self.return_none:
            return None
        return [{"detections": [{"label": self.name}]}, frame]


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("extend", {"legacy", "added"}),
        ("replace", {"replacement"}),
    ],
)
def test_surveillance_detector_modules_compose_and_run(
    execution_mode, mode, expected
):
    plugin_id = f"test.surveillance-{uuid.uuid4().hex}"
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id,
            PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    "detector",
                    "processor_item",
                    _NamedDetector,
                    execution_modes=("thread", "process"),
                    default_execution_mode="thread",
                ),
            ),
        )
    )
    module_id = f"{plugin_id}/detector"
    params = {
        "detectors": [
            {
                "module_id": module_id,
                "execution_mode": execution_mode,
                "source_ids": [7],
                "name": "legacy",
            }
        ],
        "modules": {
            "detectors": {
                "mode": mode,
                "items": [
                    {
                        "module_id": module_id,
                        "execution_mode": execution_mode,
                        "source_ids": [7],
                        "name": "added" if mode == "extend" else "replacement",
                        "delay_sec": 0.15 if mode == "extend" else 0,
                    }
                ],
            }
        },
    }
    pipeline = PipelineSurveillance()
    normalized = pipeline._normalize_pipeline_params(params)
    pipeline._init_detectors(normalized["detectors"])
    stage = pipeline.processors[-1]
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = 11
    emitted = []

    try:
        stage.start()
        for detector in stage.processors:
            assert detector.is_ready(10)
        stage.process([({}, frame)])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            emitted.extend(stage.process(None))
            labels = {
                detection["label"]
                for result in emitted
                if isinstance(result, (list, tuple)) and len(result) >= 2
                for detection in (result[0].get("detections") or [])
            }
            if expected.issubset(labels):
                break
            time.sleep(0.005)
    finally:
        stage.stop()
        stage.release()

    assert expected.issubset(labels)
    assert labels == expected
    detector_results = [
        result[0].get("detections") or []
        for result in emitted
        if isinstance(result, (list, tuple)) and len(result) >= 2
    ]
    assert len(detector_results) == 1
    assert {detection["label"] for detection in detector_results[0]} == expected


def test_detector_fanout_timeout_is_visible_to_health_and_drain():
    plugin_id = f"test.surveillance-timeout-{uuid.uuid4().hex}"
    plugin_registry.register_plugin(
        PluginSpec(
            plugin_id,
            PLUGIN_API_VERSION,
            modules=(
                ModuleSpec(
                    "detector",
                    "processor_item",
                    _NamedDetector,
                    execution_modes=("thread",),
                    default_execution_mode="thread",
                ),
            ),
        )
    )
    module_id = f"{plugin_id}/detector"
    pipeline = PipelineSurveillance()
    pipeline._init_detectors(
        [
            {
                "module_id": module_id,
                "execution_mode": "thread",
                "source_ids": [7],
                "name": "available",
            },
            {
                "module_id": module_id,
                "execution_mode": "thread",
                "source_ids": [7],
                "name": "missing",
                "delay_sec": 0.15,
                "return_none": True,
            },
        ]
    )
    stage = pipeline.processors[-1]
    stage._detector_fanout_timeout_sec = 0.05
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = 22
    emitted = []

    try:
        stage.start()
        for detector in stage.processors:
            assert detector.is_ready(10)
        stage.process([({}, frame)])
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            emitted.extend(stage.process(None))
            if stage._detector_fanout_pending:
                break
            time.sleep(0.005)

        assert pipeline.get_pending_work_summary()
        assert pipeline.get_runtime_stats()["degraded"] is False
        time.sleep(0.06)
        emitted.extend(stage.process(None))

        assert stage._detector_fanout_pending == {}
        runtime = pipeline.get_runtime_stats()
        assert runtime["degraded"] is True
        assert runtime["stages"]["detectors"] == {
            "degraded": True,
            "pending_detector_fanout": 0,
            "detector_fanout_incomplete": 1,
        }
        labels = {
            detection["label"]
            for result in emitted
            if isinstance(result, (list, tuple)) and len(result) >= 2
            for detection in (result[0].get("detections") or [])
        }
        assert labels == {"available"}
    finally:
        stage.stop()
        stage.release()
