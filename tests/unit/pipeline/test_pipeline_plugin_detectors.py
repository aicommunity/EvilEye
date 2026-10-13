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
from tests.unit.pipeline.plugin_detector_fixtures import NamedDetector as _NamedDetector


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
        ],
        fanout_timeout_sec=0.05,
        fanout_max_pending=9,
    )
    stage = pipeline.processors[-1]
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
            "detector_fanout_policy": "forward_partial",
            "detector_fanout_timeout_sec": 0.05,
            "detector_fanout_max_pending": 9,
            "pending_detector_fanout": 0,
            "detector_fanout_incomplete": 1,
            "detector_fanout_dropped": 0,
            "module_count": 2,
            "unknown_modules": 0,
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


def test_drop_frame_fanout_policy_is_explicit_and_diagnostic():
    plugin_id = f"test.surveillance-drop-{uuid.uuid4().hex}"
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
    pipeline.set_params(
        detector_fanout_policy="drop_frame",
        detector_fanout_timeout_sec=0.05,
        detector_fanout_max_pending=8,
        detectors=[
            {"module_id": module_id, "execution_mode": "thread", "source_ids": [7], "name": "available"},
            {"module_id": module_id, "execution_mode": "thread", "source_ids": [7], "name": "missing", "delay_sec": 0.15, "return_none": True},
        ],
    )
    assert pipeline.init()
    stage = pipeline.processors[-1]
    assert stage.detector_fanout_policy == "drop_frame"
    assert stage._detector_fanout_timeout_sec == 0.05
    assert stage._detector_fanout_max_pending == 8
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = 23
    emitted = []

    try:
        stage.start()
        for detector in stage.processors:
            assert detector.is_ready(10)
        emitted.extend(stage.process([({}, frame)]))
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline and stage._detector_fanout_pending:
            emitted.extend(stage.process(None))
            time.sleep(0.005)
        time.sleep(0.06)
        emitted.extend(stage.process(None))

        assert emitted == []
        runtime = pipeline.get_runtime_stats()
        assert runtime["degraded"] is True
        assert runtime["stages"]["detectors"] == {
            "degraded": True,
            "detector_fanout_policy": "drop_frame",
            "detector_fanout_timeout_sec": 0.05,
            "detector_fanout_max_pending": 8,
            "pending_detector_fanout": 0,
            "detector_fanout_incomplete": 1,
            "detector_fanout_dropped": 1,
            "module_count": 2,
            "unknown_modules": 0,
        }
    finally:
        stage.stop()
        stage.release()


def test_unknown_detector_fanout_policy_fails_pipeline_initialization():
    pipeline = PipelineSurveillance()
    pipeline.set_params(detector_fanout_policy="silently_ignore")

    with pytest.raises(ValueError, match="pipeline.detector_fanout_policy"):
        pipeline.init()


@pytest.mark.parametrize(
    "params, error",
    [
        ({"detector_fanout_timeout_sec": 0}, "detector_fanout_timeout_sec"),
        ({"detector_fanout_timeout_sec": float("inf")}, "detector_fanout_timeout_sec"),
        ({"detector_fanout_max_pending": 0}, "detector_fanout_max_pending"),
        ({"detector_fanout_max_pending": 1.5}, "detector_fanout_max_pending"),
    ],
)
def test_detector_fanout_limits_reject_invalid_pipeline_configuration(params, error):
    pipeline = PipelineSurveillance()
    pipeline.set_params(**params)

    with pytest.raises(ValueError, match=error):
        pipeline.init()


def test_explicit_detector_fanout_timeout_overrides_legacy_environment(monkeypatch):
    monkeypatch.setenv("EVILEYE_DETECTOR_FANOUT_TIMEOUT_SEC", "invalid")
    pipeline = PipelineSurveillance()
    pipeline.set_params(detector_fanout_timeout_sec=0.25)

    assert pipeline.init()
