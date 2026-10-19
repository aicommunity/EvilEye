"""Stage 1 (A1/A2): process_item error policy, restarts and legacy mp_* params."""
from __future__ import annotations

import os
import signal
import sys
import time

import pytest

from evileye.core.plugin_runtime import ItemModuleAdapter, ParallelItemModuleAdapter
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginError,
    PluginSpec,
    plugin_registry,
)


class _EveryTenthFails:
    def process_item(self, item, state):
        if item % 10 == 0:
            raise RuntimeError(f"bad item {item}")
        return item


class _AlwaysFails:
    def process_item(self, item, state):
        raise RuntimeError("always failing")


class _FailsFirstCalls:
    """Fails the first ``remaining`` calls of the process, then recovers."""

    remaining = 3

    def process_item(self, item, state):
        if _FailsFirstCalls.remaining > 0:
            _FailsFirstCalls.remaining -= 1
            raise RuntimeError("transient failure")
        return item


class _Echo:
    def process_item(self, item, state):
        return item


def _make_adapter(factory, mode, name, *, parallel=False, **params):
    plugin_id = f"test.errpolicy-{name}-{mode}"
    spec = ModuleSpec(
        "m",
        "processor_item",
        factory,
        execution_modes=(mode,),
        capabilities=("parallel_items",) if parallel else (),
    )
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    registered = plugin_registry.get_module(f"{plugin_id}/m")
    adapter_type = ParallelItemModuleAdapter if parallel else ItemModuleAdapter
    adapter = adapter_type(registered)
    adapter.set_params(module_id=f"{plugin_id}/m", execution_mode=mode, queue_size=256, **params)
    assert adapter.init() is True
    return adapter


def _drain(adapter, *, expected, timeout):
    """Collect outputs until ``expected`` arrived and no work is pending."""
    outputs = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = adapter.get()
        if result is not None:
            outputs.append(result)
            continue
        if len(outputs) >= expected and not adapter.has_pending_work():
            break
        time.sleep(0.01)
    return outputs


def _wait(predicate, timeout):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


@pytest.mark.parametrize("mode", ["thread", "process"])
def test_skip_item_survives_every_tenth_item_failing(mode):
    adapter = _make_adapter(_EveryTenthFails, mode, "tenth")
    adapter.start()
    try:
        assert adapter.is_ready(60.0)
        for index in range(1, 101):
            adapter.put(index)
        outputs = _drain(adapter, expected=90, timeout=60.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert sorted(outputs) == [i for i in range(1, 101) if i % 10]
    assert stats["item_errors"] == 10
    # ten errors inside the window are a burst: visible as degraded, but not a failure
    assert stats["degraded"] is True and stats["recent_item_errors"] == 10
    assert stats["failed"] is False
    assert stats["worker_restarts"] == 0
    assert stats["in_flight"] == 0


@pytest.mark.parametrize("mode", ["thread", "process"])
def test_parallel_workers_skip_failing_items_in_order(mode):
    adapter = _make_adapter(_EveryTenthFails, mode, "parallel", parallel=True, worker_count=2)
    adapter.start()
    try:
        assert adapter.is_ready(60.0)
        for index in range(1, 61):
            adapter.put(index)
        outputs = _drain(adapter, expected=54, timeout=60.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert outputs == [i for i in range(1, 61) if i % 10]
    assert stats["item_errors"] == 6
    assert stats["degraded"] is True and stats["failed"] is False


def test_thread_restarts_module_after_error_burst_and_recovers():
    _FailsFirstCalls.remaining = 3
    adapter = _make_adapter(
        _FailsFirstCalls, "thread", "recover", error_burst_limit=3, max_restarts=2
    )
    adapter.start()
    try:
        assert adapter.is_ready(10.0)
        for index in range(1, 4):
            adapter.put(index)
        assert _wait(lambda: adapter.get_runtime_stats()["worker_restarts"] == 1, 10.0)
        adapter.put(100)
        outputs = _drain(adapter, expected=1, timeout=10.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert outputs == [100]
    assert stats["item_errors"] == 3
    assert stats["failed"] is False  # a restart is a recent event, not a failure


def test_thread_stops_loudly_when_restart_budget_is_exhausted():
    adapter = _make_adapter(
        _AlwaysFails, "thread", "exhaust", error_burst_limit=2, max_restarts=1
    )
    adapter.start()
    try:
        assert adapter.is_ready(10.0)
        for index in range(1, 7):
            adapter.put(index)
        assert _wait(lambda: adapter.get_runtime_stats()["degraded"], 15.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert stats["worker_restarts"] == 1
    assert stats["degraded"] is True


def test_restart_policy_recreates_process_worker_after_each_error():
    adapter = _make_adapter(_EveryTenthFails, "process", "restartpolicy", error_policy="restart")
    adapter.start()
    try:
        assert adapter.is_ready(60.0)
        adapter.put(10)
        assert _wait(
            lambda: adapter.get() is None and adapter.get_runtime_stats()["worker_restarts"] >= 1,
            30.0,
        )
        adapter.put(11)
        outputs = _drain(adapter, expected=1, timeout=30.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert outputs == [11]
    assert stats["failed"] is False


@pytest.mark.skipif(sys.platform == "win32", reason="needs POSIX SIGKILL")
def test_process_worker_killed_by_sigkill_is_restarted():
    adapter = _make_adapter(_Echo, "process", "sigkill")
    adapter.start()
    try:
        assert adapter.is_ready(60.0)
        adapter.put(1)
        assert _drain(adapter, expected=1, timeout=30.0) == [1]

        pid = adapter._mp_control.processes[0].pid
        os.kill(pid, signal.SIGKILL)
        assert _wait(lambda: adapter.get_runtime_stats()["worker_restarts"] >= 1, 30.0)
        assert adapter.get_runtime_stats()["failed"] is False

        # The replacement worker needs a moment to initialize before it serves items.
        outputs = []
        deadline = time.monotonic() + 60.0
        while not outputs and time.monotonic() < deadline:
            adapter.put(2)
            outputs = _drain(adapter, expected=1, timeout=5.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()

    assert outputs and outputs[0] == 2
    assert stats["failed"] is False
    assert adapter._mp_control is None or adapter._mp_control.processes[0].pid != pid


def test_fail_stop_keeps_legacy_behavior_without_restarts():
    adapter = _make_adapter(_AlwaysFails, "thread", "failstop", error_policy="fail_stop")
    adapter.start()
    try:
        assert adapter.is_ready(10.0)
        adapter.put(1)
        assert _wait(lambda: adapter.get_runtime_stats()["degraded"], 10.0)
        stats = adapter.get_runtime_stats()
    finally:
        adapter.stop()
    assert stats["worker_restarts"] == 0


def test_legacy_mp_restart_params_map_to_policy_and_stay_out_of_module_config():
    adapter = _make_adapter(
        _Echo, "thread", "legacy",
        mp_restart_on_exit=False, mp_no_restart_exit_codes=[3, -15], prefix="x",
    )
    assert adapter._error_policy.restart_on_exit is False
    assert adapter._error_policy.no_restart_exit_codes == (-15, 3)
    assert adapter._config == {"prefix": "x"}

    default_adapter = _make_adapter(_Echo, "thread", "defaults")
    assert default_adapter._error_policy.policy == "skip_item"
    assert default_adapter._error_policy.restart_on_exit is True

    fail_stop = _make_adapter(_Echo, "thread", "failstopdefault", error_policy="fail_stop")
    assert fail_stop._error_policy.restart_on_exit is False


@pytest.mark.parametrize(
    "params, message",
    [
        ({"error_policy": "ignore"}, "error_policy"),
        ({"mp_restart_on_exit": "sometimes"}, "mp_restart_on_exit"),
        ({"mp_no_restart_exit_codes": ["abc"]}, "mp_no_restart_exit_codes"),
        ({"error_burst_limit": 0}, "error_burst_limit"),
        ({"max_restarts": -1}, "max_restarts"),
    ],
)
def test_invalid_error_policy_params_are_configuration_errors(params, message):
    plugin_id = "test.errpolicy-invalid"
    spec = ModuleSpec("m", "processor_item", _Echo, execution_modes=("thread",))
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    adapter = ItemModuleAdapter(plugin_registry.get_module(f"{plugin_id}/m"))
    with pytest.raises(PluginError, match=message):
        adapter.set_params(module_id=f"{plugin_id}/m", execution_mode="thread", **params)


def test_few_item_errors_do_not_degrade_but_a_burst_does_and_it_recovers(monkeypatch):
    monkeypatch.setenv("EVILEYE_DEGRADED_WINDOW_SEC", "0.4")
    adapter = _make_adapter(_EveryTenthFails, "thread", "threshold", error_degraded_threshold=3)
    adapter.start()
    try:
        assert adapter.is_ready(10.0)
        for index in (10, 20):
            adapter.put(index)
        _drain(adapter, expected=0, timeout=2.0)
        assert adapter.get_runtime_stats()["recent_item_errors"] == 2
        assert adapter.degraded is False

        adapter.put(30)
        assert _wait(lambda: adapter.degraded, 5.0)
        assert adapter.get_runtime_stats()["failed"] is False

        assert _wait(lambda: not adapter.degraded, 5.0)  # the window passes
        assert adapter.item_errors == 3  # cumulative counter is kept
    finally:
        adapter.stop()


@pytest.mark.parametrize("value", [0, -1, "5", True])
def test_invalid_degraded_threshold_is_a_configuration_error(value):
    plugin_id = "test.errpolicy-threshold-invalid"
    spec = ModuleSpec("m", "processor_item", _Echo, execution_modes=("thread",))
    plugin_registry.register_plugin(PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,)))
    adapter = ItemModuleAdapter(plugin_registry.get_module(f"{plugin_id}/m"))
    with pytest.raises(PluginError, match="error_degraded_threshold"):
        adapter.set_params(
            module_id=f"{plugin_id}/m", execution_mode="thread", error_degraded_threshold=value
        )


def test_is_ready_survives_a_worker_becoming_ready_during_the_poll():
    """Regression: next() on an exhausted generator raised StopIteration (empty startup error)."""
    import threading

    class _RacyEvent:
        """Reports "not set" for the all() check, then "set" when asked again."""

        def __init__(self):
            self.calls = 0

        def is_set(self):
            self.calls += 1
            return self.calls > 1

        def wait(self, timeout=None):
            return True

    adapter = _make_adapter(_Echo, "thread", "racyready")
    adapter._thread_ready_events = [_RacyEvent()]
    adapter._thread_init_failed_events = [threading.Event()]
    assert adapter.is_ready(2.0) is True
