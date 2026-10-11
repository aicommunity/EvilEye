from __future__ import annotations

import threading
import time

import pytest

from evileye.core.plugin_runtime import SourceModuleAdapter
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginError,
    PluginSpec,
    RegisteredModule,
    plugin_registry,
)


class _FiniteSource:
    def __init__(self, config=None):
        config = config or {}
        self.items = list(config.get("items", []))
        self.marker_path = config["marker_path"]
        self.index = 0

    def _mark(self, state):
        with open(self.marker_path, "a", encoding="utf-8") as marker:
            marker.write(state + "\n")

    def open(self):
        self.index = 0
        self._mark("open")

    def read(self):
        if self.index >= len(self.items):
            return None
        item = self.items[self.index]
        self.index += 1
        return item

    def close(self):
        self._mark("close")


class _BlockingReadSource:
    def __init__(self, config=None):
        config = config or {}
        self.started = config["started"]
        self.release_read = config["release_read"]
        self.closed = config["closed"]

    def open(self):
        pass

    def read(self):
        self.started.set()
        self.release_read.wait(timeout=5)
        return None

    def close(self):
        self.closed.set()


def _register_source(plugin_id, factory, modes):
    spec = ModuleSpec(
        "source",
        "source",
        factory,
        execution_modes=modes,
    )
    registered = RegisteredModule(plugin_id, spec)
    plugin_registry.register_plugin(
        PluginSpec(plugin_id, PLUGIN_API_VERSION, modules=(spec,))
    )
    return registered


@pytest.mark.parametrize("execution_mode", ["thread", "process"])
def test_finite_source_closes_once_after_eof(execution_mode, tmp_path):
    plugin_id = f"test.source-lifecycle-{execution_mode}"
    module_id = f"{plugin_id}/source"
    registered = _register_source(plugin_id, _FiniteSource, (execution_mode,))
    marker_path = tmp_path / f"{execution_mode}.lifecycle"
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=module_id,
        execution_mode=execution_mode,
        config={
            "marker_path": str(marker_path),
            "items": [{"frame_id": 1}, {"frame_id": 2}],
        },
    )
    assert source.init() is True
    source.start()
    try:
        deadline = time.monotonic() + (15 if execution_mode == "process" else 2)
        items = []
        while len(items) < 2 and time.monotonic() < deadline:
            items.extend(source.get())
            if len(items) < 2:
                time.sleep(0.02)
        assert [item["frame_id"] for item in items] == [1, 2]
    finally:
        source.stop()

    assert marker_path.read_text(encoding="utf-8").splitlines() == ["open", "close"]
    stats = source.get_runtime_stats()
    assert stats["worker_running"] is False
    assert stats["finished"] is True
    assert stats["degraded"] is False


def test_blocked_thread_source_remains_visible_until_read_returns():
    started = threading.Event()
    release_read = threading.Event()
    closed = threading.Event()
    plugin_id = "test.blocked-source"
    registered = _register_source(plugin_id, _BlockingReadSource, ("thread",))
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=f"{plugin_id}/source",
        execution_mode="thread",
        config={
            "started": started,
            "release_read": release_read,
            "closed": closed,
        },
    )
    source._thread_stop_timeout_secs = 0.05
    assert source.init() is True
    source.start()
    assert started.wait(timeout=2)

    source.stop()
    stats = source.get_runtime_stats()
    assert stats["worker_running"] is True
    assert stats["finished"] is False
    assert stats["degraded"] is True
    assert "did not stop before timeout" in stats["last_error"]
    with pytest.raises(PluginError, match="previous worker is running"):
        source.start()

    release_read.set()
    deadline = time.monotonic() + 2
    while source.is_running() and time.monotonic() < deadline:
        time.sleep(0.01)
    source.stop()

    assert closed.wait(timeout=1)
    stats = source.get_runtime_stats()
    assert stats["worker_running"] is False
    assert stats["finished"] is True
    assert stats["degraded"] is True


class _BlockingProcessSource:
    def __init__(self, config=None):
        self.marker_path = (config or {})["marker_path"]

    def open(self):
        pass

    def read(self):
        with open(self.marker_path, "w", encoding="utf-8") as marker:
            marker.write("reading")
        time.sleep(20)
        return None

    def close(self):
        pass


def test_blocked_process_source_is_terminated_and_reported(tmp_path):
    plugin_id = "test.blocked-process-source"
    registered = _register_source(plugin_id, _BlockingProcessSource, ("process",))
    marker_path = tmp_path / "process-reading.txt"
    source = SourceModuleAdapter(registered)
    source.set_params(
        module_id=f"{plugin_id}/source",
        execution_mode="process",
        config={"marker_path": str(marker_path)},
    )
    source._process_stop_timeout_secs = 0.05
    source._process_terminate_timeout_secs = 1.0
    assert source.init() is True
    source.start()

    deadline = time.monotonic() + 10
    while not marker_path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert marker_path.exists()

    source.stop()
    stats = source.get_runtime_stats()
    assert stats["worker_running"] is False
    assert stats["finished"] is True
    assert stats["degraded"] is True
    assert "forced termination" in stats["last_error"]
