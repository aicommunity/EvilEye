"""error_policy for batch processors, process event detectors and sources."""
from __future__ import annotations

import os
import signal
import sys
import time

import pytest

from evileye.core.contracts import EventUpdate
from evileye.core.plugin_runtime import (
    BatchProcessorModuleAdapter,
    EventDetectorModuleAdapter,
    SourceModuleAdapter,
)
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginError,
    PluginSpec,
    plugin_registry,
)
from evileye.events_detectors.alarm_event import AlarmEvent
from evileye.events_detectors.event_registry import EventDetectorContext


def _wait(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def _register(plugin_id, spec):
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    return plugin_registry.get_module(f"{plugin_id}/{spec.module_id}")


# ------------------------------------------------------------------ batch


class _FlakyBatch:
    instances = 0

    def __init__(self, config=None):
        _FlakyBatch.instances += 1
        self.always_fail = bool((config or {}).get("always_fail"))

    def process_batch(self, batch, state):
        if self.always_fail or "boom" in batch:
            raise RuntimeError("batch failure")
        return [f"ok:{sorted(batch)}"]


def _batch_adapter(name, **params):
    registered = _register(f"test.batch-{name}", ModuleSpec("b", "batch_processor", _FlakyBatch, ("thread",)))
    adapter = BatchProcessorModuleAdapter(registered)
    adapter.set_params(module_id=registered.qualified_id, execution_mode="thread", **params)
    assert adapter.init() is True
    adapter.start()
    return adapter


def test_batch_failure_is_skipped_and_the_stage_keeps_working():
    adapter = _batch_adapter("skip")
    assert adapter.process_batch({"a": 1}) == ["ok:['a']"]
    assert adapter.process_batch({"boom": 1}) == []
    assert adapter.process_batch({"b": 1}) == ["ok:['b']"]
    stats = adapter.get_runtime_stats()
    assert stats["item_errors"] == 1 and stats["failed"] is False and stats["degraded"] is False


def test_batch_burst_restarts_the_module_then_stops_when_the_budget_is_spent():
    _FlakyBatch.instances = 0
    adapter = _batch_adapter("burst", error_burst_limit=2, max_restarts=1, config={"always_fail": True})
    assert _FlakyBatch.instances == 1
    assert adapter.process_batch({"x": 1}) == []  # error 1: skipped
    assert adapter.process_batch({"x": 1}) == []  # error 2: burst -> restart
    assert adapter.worker_restarts == 1 and _FlakyBatch.instances == 2
    assert adapter.process_batch({"x": 1}) == []
    with pytest.raises(RuntimeError, match="batch failure"):
        adapter.process_batch({"x": 1})  # burst again, budget spent -> propagate
    assert adapter.get_runtime_stats()["failed"] is True


def test_batch_fail_stop_keeps_the_old_behavior():
    adapter = _batch_adapter("failstop", error_policy="fail_stop")
    with pytest.raises(RuntimeError, match="batch failure"):
        adapter.process_batch({"boom": 1})
    assert adapter.degraded is True


def test_batch_policy_params_stay_out_of_module_config():
    adapter = _batch_adapter("params", error_burst_limit=7, prefix="x")
    assert adapter._config == {"prefix": "x"}
    assert "error_burst_limit" not in adapter._module_params


# ------------------------------------------------------------------ events (process)


def make_flaky_event_module(config):
    return _FlakyEvent(config)


class _FlakyEvent:
    def __init__(self, config):
        self.fail_sequences = set((config or {}).get("fail_sequences", []))

    def process_update(self, update, state):
        if update.sequence in self.fail_sequences:
            raise RuntimeError(f"bad update {update.sequence}")
        return [
            AlarmEvent(
                "flaky_alarm", severity="info", source_id=update.source_id,
                details={"sequence": update.sequence}, alarm_id=f"a-{update.sequence}",
            )
        ]


def _event_detector(**params):
    plugin_id = "test.stage5-events"
    module_id = f"{plugin_id}/flaky"
    if plugin_registry.get_module(module_id) is None:
        _register(plugin_id, ModuleSpec(
            "flaky", "event_detector", make_flaky_event_module,
            execution_modes=("process",), capabilities=("event_updates",),
            default_execution_mode="process",
        ))
    detector = EventDetectorModuleAdapter(plugin_registry.get_module(module_id), EventDetectorContext())
    detector.set_params(execution_mode="process", queue_size=8, **params)
    assert detector.init() is True
    detector.start()
    return detector


def _update(sequence):
    return EventUpdate(
        sequence=sequence, kind="object_snapshot", source_id=5,
        timestamp="2026-10-11T12:00:00Z", payload={"active": [], "lost": []},
    )


def _collect(detector, count, timeout=15.0):
    events = []
    _wait(lambda: (events.extend(detector.get()) or len(events) >= count), timeout)
    return events


def test_event_detector_defaults_to_fail_stop():
    detector = _event_detector(fail_sequences=[1])
    try:
        assert detector._error_policy.policy == "fail_stop"
        assert detector._error_policy.restart_on_exit is False
        detector.put(_update(1))
        assert _wait(lambda: detector.get() is not None and detector.degraded, 10.0)
        assert detector.get_runtime_stats()["failed"] is True
    finally:
        detector.stop()


def test_event_detector_skip_item_drops_only_the_bad_update():
    detector = _event_detector(error_policy="skip_item", fail_sequences=[1, 3])
    try:
        for sequence in range(5):
            detector.put(_update(sequence))
        events = _collect(detector, 3)
        assert sorted(event.details["sequence"] for event in events) == [0, 2, 4]
        assert _wait(lambda: detector.get() is not None and detector.item_errors == 2, 5.0)
        stats = detector.get_runtime_stats()
        assert stats["failed"] is False and stats["worker_restarts"] == 0
        assert stats["degraded"] is False  # 2 errors are below the threshold of 5
    finally:
        detector.stop()


def test_event_detector_error_burst_restarts_the_worker():
    detector = _event_detector(error_policy="skip_item", error_burst_limit=2, fail_sequences=[1, 2])
    try:
        first_pid = detector._mp_control.processes[0].pid
        detector.put(_update(1))
        detector.put(_update(2))
        assert _wait(lambda: detector.get() is not None and detector.worker_restarts >= 1, 30.0)
        assert detector._mp_control.processes[0].pid != first_pid
        assert detector.get_runtime_stats()["failed"] is False
        events = []
        deadline = time.monotonic() + 30.0
        while not events and time.monotonic() < deadline:
            detector.put(_update(10))
            events = _collect(detector, 1, timeout=3.0)
        assert events and events[0].details["sequence"] == 10
        assert detector.get_runtime_stats()["failed"] is False
    finally:
        detector.stop()


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX SIGKILL")
def test_event_worker_killed_by_sigkill_is_restarted_when_policy_allows():
    detector = _event_detector(error_policy="skip_item")
    try:
        os.kill(detector._mp_control.processes[0].pid, signal.SIGKILL)
        assert _wait(lambda: detector.get() is not None and detector.worker_restarts >= 1, 30.0)
        assert detector.degraded is True and detector.get_runtime_stats()["failed"] is False
        events = []
        deadline = time.monotonic() + 30.0
        while not events and time.monotonic() < deadline:
            detector.put(_update(7))
            events = _collect(detector, 1, timeout=3.0)
        assert events and events[0].details["sequence"] == 7
    finally:
        detector.stop()


# ------------------------------------------------------------------ sources


class _FlakySource:
    """Yields 1..n; ``read`` raises on the listed call numbers (1-based)."""

    opens = 0

    def __init__(self, config=None):
        config = config or {}
        self.total = int(config.get("total", 3))
        self.fail_calls = set(config.get("fail_calls", []))
        self.calls = 0
        self.index = 0

    def open(self):
        _FlakySource.opens += 1

    def read(self):
        self.calls += 1
        if self.calls in self.fail_calls:
            raise RuntimeError(f"read failure {self.calls}")
        if self.index >= self.total:
            return None
        self.index += 1
        return self.index

    def close(self):
        pass


def _source(name, mode="thread", **params):
    registered = _register(f"test.source-{name}", ModuleSpec("s", "source", _FlakySource, (mode,)))
    adapter = SourceModuleAdapter(registered)
    adapter.set_params(module_id=registered.qualified_id, execution_mode=mode, **params)
    assert adapter.init() is True
    adapter.start()
    return adapter


def _read_all(source, timeout=20.0):
    items = []
    _wait(lambda: (items.extend(source.get()) or source.get_runtime_stats()["finished"]), timeout)
    items.extend(source.get())
    return items


@pytest.mark.parametrize("mode", ["thread", "process"])
def test_source_read_errors_are_retried_instead_of_ending_the_source(mode):
    source = _source(f"skip-{mode}", mode, config={"total": 3, "fail_calls": [2, 4]})
    try:
        items = _read_all(source)
        stats = source.get_runtime_stats()
    finally:
        source.stop()
    assert items == [1, 2, 3]
    if mode == "thread":  # a process worker keeps its counters in the child
        assert stats["item_errors"] == 2
    assert stats["degraded"] is False and stats["failed"] is False


def test_source_error_burst_reopens_the_source():
    _FlakySource.opens = 0
    source = _source("burst", error_burst_limit=2, config={"total": 2, "fail_calls": [1, 2]})
    try:
        items = _read_all(source)
        stats = source.get_runtime_stats()
    finally:
        source.stop()
    assert items == [1, 2]
    assert _FlakySource.opens == 2
    assert stats["worker_restarts"] == 1 and stats["failed"] is False


def test_source_fail_stop_ends_the_source_and_marks_it_degraded():
    source = _source("failstop", error_policy="fail_stop", config={"total": 3, "fail_calls": [2]})
    try:
        items = _read_all(source)
        stats = source.get_runtime_stats()
    finally:
        source.stop()
    assert items == [1]
    assert stats["degraded"] is True and stats["failed"] is True and stats["finished"] is True


def test_source_restart_budget_exhaustion_ends_the_source():
    source = _source(
        "budget", error_burst_limit=1, max_restarts=1,
        config={"total": 5, "fail_calls": [1, 2, 3, 4, 5, 6]},
    )
    try:
        _read_all(source)
        stats = source.get_runtime_stats()
    finally:
        source.stop()
    assert stats["failed"] is True and stats["finished"] is True


def test_invalid_policy_values_are_configuration_errors_for_all_adapters():
    registered = _register("test.source-invalid", ModuleSpec("s", "source", _FlakySource, ("thread",)))
    adapter = SourceModuleAdapter(registered)
    with pytest.raises(PluginError, match="error_policy"):
        adapter.set_params(module_id=registered.qualified_id, execution_mode="thread", error_policy="ignore")
    registered = _register("test.batch-invalid", ModuleSpec("b", "batch_processor", _FlakyBatch, ("thread",)))
    batch = BatchProcessorModuleAdapter(registered)
    with pytest.raises(PluginError, match="error_burst_limit"):
        batch.set_params(module_id=registered.qualified_id, execution_mode="thread", error_burst_limit=0)
