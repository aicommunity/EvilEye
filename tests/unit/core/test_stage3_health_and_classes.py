"""Stage 3: class id remapping (B5), sliding-window health (B6)."""
from __future__ import annotations

import time
import uuid

import pytest

from evileye.core.class_manager import ClassManager
from evileye.core.frame import Frame
from evileye.core.health_window import RollingEventCounter, degraded_window_seconds
from evileye.core.plugin_runtime import ItemModuleAdapter
from evileye.core.plugins import PLUGIN_API_VERSION, ModuleSpec, PluginSpec, plugin_registry
from evileye.pipelines.pipeline_surveillance import PipelineSurveillance
from tests.unit.pipeline.plugin_detector_fixtures import ClassedDetector


class _FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_rolling_counter_forgets_old_events_but_keeps_the_total():
    clock = _FakeClock()
    counter = RollingEventCounter(window_sec=10, clock=clock)
    counter.record()
    clock.now += 4
    counter.record(2)
    assert (counter.recent(), counter.total, counter.active()) == (3, 3, True)
    clock.now += 7  # first event is now 11 s old
    assert counter.recent() == 2
    clock.now += 10
    assert (counter.recent(), counter.total, counter.active()) == (0, 3, False)
    counter.reset()
    assert counter.total == 0


def test_degraded_window_comes_from_environment(monkeypatch):
    monkeypatch.delenv("EVILEYE_DEGRADED_WINDOW_SEC", raising=False)
    assert degraded_window_seconds() == 60.0
    monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", "5")
    assert degraded_window_seconds() == 5.0
    for bad in ("0", "-3", "abc"):
        monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", bad)
        assert degraded_window_seconds() == 60.0


def _item_adapter(**params):
    plugin_id = f"test.stage3-{uuid.uuid4().hex}"
    spec = ModuleSpec(
        "m", "processor_item", ClassedDetector, execution_modes=("thread",),
        capabilities=("model_class_mapping",),
    )
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    adapter = ItemModuleAdapter(plugin_registry.get_module(f"{plugin_id}/m"))
    adapter.set_params(module_id=f"{plugin_id}/m", execution_mode="thread", **params)
    assert adapter.init()
    return adapter


def test_input_drops_degrade_only_inside_the_window(monkeypatch):
    monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", "0.2")
    adapter = _item_adapter()
    assert adapter.degraded is False

    adapter._record_input_drop()
    assert adapter.degraded is True
    assert adapter.get_runtime_stats()["recent_overload_events"] == 1

    time.sleep(0.35)
    stats = adapter.get_runtime_stats()
    assert adapter.degraded is False and stats["degraded"] is False
    assert stats["input_queue_dropped"] == 1  # cumulative counter is kept
    assert stats["failed"] is False


def test_real_failure_stays_degraded_until_reset(monkeypatch):
    monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", "0.1")
    adapter = _item_adapter()
    adapter.degraded = True
    time.sleep(0.25)
    assert adapter.degraded is True and adapter.get_runtime_stats()["failed"] is True
    adapter.degraded = False
    assert adapter.degraded is False


def test_full_input_queue_is_transient_not_permanent(monkeypatch):
    monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", "0.2")
    adapter = _item_adapter(queue_size=1)
    adapter._input_queue.put_nowait("occupied")
    with pytest.raises(RuntimeError, match="input queue is full"):
        adapter.put("not-a-frame")  # non-frame work is rejected instead of dropped
    assert adapter.degraded is True
    time.sleep(0.35)
    assert adapter.degraded is False
    assert adapter.input_queue_rejected == 1


# ---------------------------------------------------------------- class ids (B5)


def test_colliding_class_ids_are_remapped_by_name():
    manager = ClassManager()
    yolo = manager.register_detector_mapping({"person": 0, "car": 2}, "yolo")
    helmets = manager.register_detector_mapping({"helmet": 0, "vest": 1}, "ppe")
    same_names = manager.register_detector_mapping({"person": 0}, "second-yolo")
    renumbered = manager.register_detector_mapping({"car": 7}, "other-model")

    assert yolo == {0: 0, 2: 2}
    assert helmets == {0: 3, 1: 1}  # id 0 is taken by "person"; id 1 is free
    assert same_names == {0: 0}
    assert renumbered == {7: 2}  # same class name, different local id
    assert manager.get_class_id("helmet") == 3
    assert manager.get_class_name(3) == "helmet"
    assert manager.get_class_id("vest") == 1
    assert manager.get_class_mapping() == {"person": 0, "car": 2, "helmet": 3, "vest": 1}


def test_duplicate_local_ids_inside_one_model_are_reported():
    manager = ClassManager()
    remap = manager.register_detector_mapping({"a": 0, "b": 0}, "odd-model")
    assert remap == {0: 0}
    assert manager.has_conflicts()


def _classed_pipeline():
    plugin_id = f"test.stage3-classes-{uuid.uuid4().hex}"
    spec = ModuleSpec(
        "det", "processor_item", ClassedDetector, execution_modes=("thread",),
        capabilities=("model_class_mapping",),
    )
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    module_id = f"{plugin_id}/det"
    pipeline = PipelineSurveillance()
    pipeline._init_detectors([
        {"module_id": module_id, "execution_mode": "thread", "source_ids": [7],
         "name": "person", "class_id": 0, "mapping": {"person": 0}},
        {"module_id": module_id, "execution_mode": "thread", "source_ids": [7],
         "name": "helmet", "class_id": 0, "mapping": {"helmet": 0}},
    ])
    return pipeline


def _run_stage(stage, frame_id=1):
    frame = Frame()
    frame.source_id = 7
    frame.frame_id = frame_id
    emitted = []
    stage.start()
    try:
        for detector in stage.processors:
            assert detector.is_ready(10)
        stage.process([({}, frame)])
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not emitted:
            emitted.extend(stage.process(None))
            time.sleep(0.005)
    finally:
        stage.stop()
        stage.release()
    return emitted


def test_fanout_translates_class_ids_of_each_detector_to_the_global_space():
    pipeline = _classed_pipeline()
    stage = pipeline.processors[-1]
    manager = ClassManager()
    for index, detector in enumerate(stage.processors):
        mapping = {"person": 0} if index == 0 else {"helmet": 0}
        remap = manager.register_detector_mapping(mapping, f"detector-{index}")
        assert stage.set_class_id_remap(detector, remap) is True

    emitted = _run_stage(stage)

    assert len(emitted) == 1
    ids = {d["label"]: d["class_id"] for d in emitted[0][0]["detections"]}
    assert ids == {"person": 0, "helmet": 1}


def test_without_a_remap_colliding_ids_stay_indistinguishable():
    pipeline = _classed_pipeline()
    emitted = _run_stage(pipeline.processors[-1])
    assert {d["class_id"] for d in emitted[0][0]["detections"]} == {0}


def test_set_class_id_remap_ignores_foreign_processors_and_identity():
    pipeline = _classed_pipeline()
    stage = pipeline.processors[-1]
    assert stage.set_class_id_remap(object(), {0: 5}) is False
    assert stage.set_class_id_remap(stage.processors[0], {0: 0, 1: 1}) is True
    assert stage._class_id_remap == {}
