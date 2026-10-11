from __future__ import annotations

import json
import time
from datetime import datetime
from types import SimpleNamespace

import pytest

from evileye.core.contracts import EventUpdate
from evileye.core.plugins import (
    PLUGIN_API_VERSION,
    ModuleSpec,
    PluginError,
    PluginSpec,
    plugin_registry,
)
from evileye.core.plugin_runtime import EventDetectorModuleAdapter
from evileye.events_detectors.alarm_event import AlarmEvent
from evileye.events_detectors.event_registry import EventDetectorContext


class _ProcessEventModule:
    def __init__(self, config):
        self.config = dict(config)

    def process_update(self, update, state):
        if self.config.get("fail"):
            raise RuntimeError("intentional rule failure")
        active = update.payload.get("active", [])
        return [
            AlarmEvent(
                "ppe_violation",
                severity="critical",
                source_id=update.source_id,
                details={
                    "rule": self.config.get("rule", "hardhat_required"),
                    "object_ids": [item["object_id"] for item in active],
                    "sequence": update.sequence,
                },
                timestamp=datetime(2026, 10, 11, 12, 0, 0),
                alarm_id=f"ppe-{update.sequence}",
            )
        ]


def make_process_event_module(config):
    if config.get("invalid_contract"):
        return object()
    return _ProcessEventModule(config)


def _validate_process_event_config(config):
    allowed = {"rule", "fail", "invalid_contract"}
    unknown = set(config) - allowed
    if unknown:
        raise ValueError(f"unknown event config keys: {sorted(unknown)}")
    return config


def _register_module():
    module_id = "tests.runtime/process_event"
    if plugin_registry.get_module(module_id) is None:
        plugin_registry.register_plugin(
            PluginSpec(
                "tests.runtime",
                PLUGIN_API_VERSION,
                modules=(
                    ModuleSpec(
                        "process_event",
                        "event_detector",
                        make_process_event_module,
                        execution_modes=("process",),
                        capabilities=("event_updates",),
                        config_schema=_validate_process_event_config,
                        default_execution_mode="process",
                    ),
                ),
            )
        )
    return plugin_registry.get_module(module_id)


class _ObjectsHandler:
    def __init__(self):
        self.objects = {
            "active": SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        object_id=42,
                        global_id=8,
                        source_id=5,
                        class_id=0,
                        frame_id=17,
                        time_stamp=datetime(2026, 10, 11, 11, 59, 59),
                        track=SimpleNamespace(bounding_box=[1.0, 2.0, 3.0, 4.0]),
                        attributes={"hardhat": {"state": "missing"}},
                        history=[
                            SimpleNamespace(
                                object_id=42,
                                global_id=8,
                                source_id=5,
                                class_id=0,
                                frame_id=16,
                                time_stamp=datetime(2026, 10, 11, 11, 59, 58),
                                track=SimpleNamespace(bounding_box=[0.0, 2.0, 3.0, 4.0]),
                            )
                        ],
                    )
                ]
            ),
            "lost": SimpleNamespace(objects=[]),
        }

    def get(self, kind, source_id):
        return self.objects[kind]


def _make_adapter(*, handler=None, **config):
    registered = _register_module()
    context = EventDetectorContext(
        objects_handler=handler,
        pipeline_source_ids=(5,) if handler is not None else (),
    )
    detector = EventDetectorModuleAdapter(registered, context)
    detector.set_params(execution_mode="process", queue_size=4, **config)
    assert detector.init() is True
    detector.start()
    return detector


def _wait_for_events(detector, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = detector.get()
        if events:
            return events
        time.sleep(0.02)
    return []


def test_process_event_detector_receives_serializable_object_updates_and_stops():
    detector = _make_adapter(handler=_ObjectsHandler(), rule="ppe_check")
    child = detector._mp_control.processes[0]
    try:
        detector.update()
        events = _wait_for_events(detector)

        assert len(events) == 1
        assert events[0].alarm_type == "ppe_violation"
        assert events[0].source_id == 5
        assert events[0].details == {
            "rule": "ppe_check",
            "object_ids": [42],
            "sequence": 0,
        }
        assert detector.get_runtime_stats()["degraded"] is False
    finally:
        detector.stop()

    assert detector._update_thread is None
    assert detector._mp_control is None
    assert not child.is_alive()


def test_process_event_detector_reports_worker_failure():
    detector = _make_adapter(fail=True)
    try:
        detector.put(
            EventUpdate(
                sequence=1,
                kind="object_snapshot",
                source_id=5,
                timestamp="2026-10-11T12:00:00Z",
                payload={"active": [], "lost": []},
            )
        )
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            detector.get()
            if detector.degraded:
                break
            time.sleep(0.02)

        assert detector.degraded is True
        assert "intentional rule failure" in detector.last_error
        with pytest.raises(PluginError, match="input queue is full"):
            for sequence in range(10, 20):
                detector.put(
                    EventUpdate(
                        sequence=sequence,
                        kind="object_snapshot",
                        source_id=5,
                        payload={"active": [], "lost": []},
                    )
                )
        assert "queue is full" in detector.last_error
    finally:
        detector.stop()


def test_process_event_mode_requires_event_update_capability():
    registered = _register_module()
    unsupported = ModuleSpec(
        "unsupported_process_event",
        "event_detector",
        make_process_event_module,
        execution_modes=("process",),
        capabilities=(),
    )
    plugin_registry.register_plugin(
        PluginSpec("tests.unsupported", PLUGIN_API_VERSION, modules=(unsupported,))
    )
    adapter = EventDetectorModuleAdapter(
        plugin_registry.get_module("tests.unsupported/unsupported_process_event"),
        EventDetectorContext(),
    )

    with pytest.raises(PluginError, match="event_updates or event_commands"):
        adapter.set_params(execution_mode="process")


def test_events_service_process_alarm_reaches_json_journal(tmp_path):
    from evileye.controller.services.events_service import EventsService
    from evileye.database_controller.json_adapter_alarm_events import JsonAdapterAlarmEvents
    from evileye.events_control.events_processor import EventsProcessor
    from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
    from evileye.api.core.journal_grouping import group_events_rows

    class _Pipeline:
        def get_sources(self):
            return [object()]

    class _SubscribedObjectsHandler(_ObjectsHandler):
        def __init__(self):
            super().__init__()
            self.subscribers = []

        def subscribe(self, *subscribers):
            self.subscribers.extend(subscribers)

    handler = _SubscribedObjectsHandler()
    service = EventsService()
    module_id = "tests.runtime/process_event"
    service.initialize_detectors(
        {
            "enabled": [module_id],
            module_id: {"execution_mode": "process", "rule": "from_service"},
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector(module_id)
    assert detector in handler.subscribers

    service.start_detectors()
    alarm_adapter = JsonAdapterAlarmEvents(None)
    alarm_adapter.set_params(image_dir=str(tmp_path))
    alarm_adapter.init()
    alarm_adapter.start()
    processor = EventsProcessor([alarm_adapter], None)
    processor.init()
    processor.start()
    try:
        handler.subscribers[0].update()
        controller = service.get_detectors_controller()
        deadline = time.monotonic() + 5.0
        snapshot = {}
        while time.monotonic() < deadline:
            if controller.flush_once():
                snapshot = controller.get()
                break
            time.sleep(0.02)

        assert len(snapshot["process_event"]) == 1
        alarm = snapshot["process_event"][0]
        assert alarm.details["rule"] == "from_service"
        assert processor.put(snapshot) is True

        path = (
            tmp_path
            / "Events"
            / "2026-10-11"
            / "Metadata"
            / "alarm_events.json"
        )
        deadline = time.monotonic() + 2.0
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        records = json.loads(path.read_text(encoding="utf-8"))
        assert records[0]["alarm_id"] == alarm.alarm_id

        source = JsonLabelJournalDataSource(str(tmp_path))
        row = source._map_item(records[0], "alarm", "2026-10-11", 0)
        assert group_events_rows([row])[0]["event"] == "ppe_violation"
    finally:
        processor.stop()
        alarm_adapter.stop()
        service.release()


def test_process_event_detector_startup_contract_failure_is_explicit():
    registered = _register_module()
    detector = EventDetectorModuleAdapter(registered, EventDetectorContext())
    detector.set_params(execution_mode="process", invalid_contract=True)
    assert detector.init() is True

    with pytest.raises(PluginError, match="must implement process_update"):
        detector.start()

    assert detector.get_runtime_stats()["degraded"] is True
    assert "Worker initialization failed" in detector.get_runtime_stats()["last_error"]
    detector.stop()


def test_host_update_notification_overflow_is_reported():
    detector = EventDetectorModuleAdapter(_register_module(), EventDetectorContext())
    detector.set_params(execution_mode="process", queue_size=1)
    assert detector.init() is True

    detector.update()
    detector.update()

    stats = detector.get_runtime_stats()
    assert stats["degraded"] is True
    assert stats["update_notifications_dropped"] == 1
    assert "notification was rejected" in stats["last_error"]
    detector.stop()


def test_events_service_fails_start_when_process_detector_contract_is_invalid():
    from evileye.controller.services.events_service import EventsService

    class _Pipeline:
        def get_sources(self):
            return []

    class _ObjectsHandler:
        def subscribe(self, *subscribers):
            pass

    module_id = "tests.runtime/process_event"
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": [module_id],
            module_id: {"execution_mode": "process", "invalid_contract": True},
        },
        _Pipeline(),
        _ObjectsHandler(),
        use_database=False,
    )
    detector = service.get_detector(module_id)
    try:
        with pytest.raises(RuntimeError, match="must implement process_update"):
            service.start_detectors()
        assert detector.get_runtime_stats()["degraded"] is True
    finally:
        service.release()


def test_builtin_system_events_detector_uses_process_command_contract():
    from evileye.controller.services.events_service import EventsService
    from evileye.events_detectors.event_registry import register_builtins

    register_builtins()
    registered = plugin_registry.get_module("SystemEventsDetector")
    assert tuple(registered.spec.execution_modes) == ("process",)
    assert "event_commands" in registered.spec.capabilities

    class _Pipeline:
        def get_sources(self):
            return []

    class _ObjectsHandler:
        def subscribe(self, *subscribers):
            pass

    service = EventsService()
    service.initialize_detectors(
        {"enabled": ["SystemEventsDetector"]},
        _Pipeline(),
        _ObjectsHandler(),
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector("SystemEventsDetector")
    detector.emit_started()  # queued before spawn worker startup
    service.start_detectors()
    controller = service.get_detectors_controller()

    try:
        deadline = time.monotonic() + 5.0
        snapshot = {}
        while time.monotonic() < deadline:
            if controller.flush_once():
                snapshot = controller.get()
                break
            time.sleep(0.02)

        events = snapshot["SystemEventsDetector"]
        assert len(events) == 1
        assert events[0].event_type == "SystemStart"
        assert events[0].get_name() == "SystemEvent"
    finally:
        service.release()


def test_process_event_detector_drains_accepted_events_on_graceful_stop():
    detector = _make_adapter()
    try:
        detector.put(
            EventUpdate(
                sequence=23,
                kind="object_snapshot",
                source_id=5,
                timestamp="2026-10-11T12:00:00Z",
                payload={"active": [{"object_id": 99}], "lost": []},
            )
        )
        detector.stop()
        events = detector.get()

        assert len(events) == 1
        assert events[0].details["object_ids"] == [99]
        assert events[0].alarm_id == "ppe-23"
        assert detector.get() == []
    finally:
        detector.stop()
