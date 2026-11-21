from __future__ import annotations

import json
import time
from datetime import datetime

import pytest

from evileye.database_controller.json_adapter_alarm_events import JsonAdapterAlarmEvents
from evileye.events_control.events_controller import EventsDetectorsController
from evileye.events_control.events_processor import EventsProcessor
from evileye.events_detectors.alarm_event import AlarmEvent
from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
from evileye.api.core.journal_grouping import group_events_rows


class _AlarmDetector:
    def __init__(self, event):
        self.event = event
        self.delivered = False

    def get_name(self):
        return "SafetyRule"

    def get(self):
        if self.delivered:
            return []
        self.delivered = True
        return [self.event]


def test_alarm_flows_through_controller_storage_and_journal(tmp_path):
    alarm = AlarmEvent(
        "ppe_violation",
        severity="critical",
        source_id=7,
        source_name="camera-7",
        details={"person_id": 12, "rule": "hardhat_required"},
        timestamp=datetime(2026, 10, 9, 10, 30, 0),
        alarm_id="stable-alarm-1",
    )

    detector_controller = EventsDetectorsController([_AlarmDetector(alarm)])
    detector_controller.init()
    assert detector_controller.flush_once()
    snapshot = detector_controller.get()
    assert snapshot["SafetyRule"][0].alarm_id == alarm.alarm_id

    json_adapter = JsonAdapterAlarmEvents(None)
    json_adapter.set_params(image_dir=str(tmp_path))
    json_adapter.init()
    json_adapter.start()
    processor = EventsProcessor([json_adapter], None)
    processor.init()
    processor.start()
    try:
        assert processor.put(snapshot)
        file_path = tmp_path / "Events" / "2026-10-09" / "Metadata" / "alarm_events.json"
        deadline = time.monotonic() + 2.0
        while not file_path.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert file_path.exists()

        # Re-delivery is idempotent for the stable alarm identifier.
        json_adapter.insert(alarm)
        records = json.loads(file_path.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert records[0]["severity"] == "critical"
        assert records[0]["details"]["rule"] == "hardhat_required"

        data_source = JsonLabelJournalDataSource(str(tmp_path))
        row = data_source._map_item(records[0], "alarm", "2026-10-09", 0)
        assert row["event_type"] == "alarm"
        assert row["source_name"] == "camera-7"

        display_row = group_events_rows([row])[0]
        assert display_row["event"] == "ppe_violation"
        assert "critical" in display_row["information"]
    finally:
        processor.stop()
        json_adapter.stop()
        detector_controller.stop()


def test_event_controller_thread_starts_and_stops_cleanly():
    controller = EventsDetectorsController([])
    controller.init()

    controller.start()
    assert controller.is_running() is True
    controller.stop()

    assert controller.is_running() is False


def test_detector_failure_is_reported_without_blocking_other_alarms():
    class _BrokenDetector:
        def get_name(self):
            return "BrokenRule"

        def get(self):
            raise RuntimeError("rule evaluation failed")

    alarm = AlarmEvent("ppe_violation", alarm_id="healthy-alarm")
    controller = EventsDetectorsController([_BrokenDetector(), _AlarmDetector(alarm)])
    controller.init()

    assert controller.flush_once() is True
    assert controller.get()["SafetyRule"][0].alarm_id == "healthy-alarm"
    stats = controller.get_runtime_stats()
    assert stats["degraded"] is True
    assert "rule evaluation failed" in stats["last_error"]
    controller.stop()


def test_entry_point_event_detector_can_emit_generic_alarm():
    from evileye.controller.services.events_service import EventsService
    from evileye.core.base_class import EvilEyeBase
    from evileye.core.plugins import PLUGIN_API_VERSION, ModuleSpec, PluginError, PluginSpec, plugin_registry
    from evileye.events_detectors.event_registry import EventDetectorContext
    from evileye.events_detectors.system_events_detector import SystemEventsDetector

    alarm = AlarmEvent(
        "ppe_violation",
        source_id=3,
        details={"rule": "hardhat_required"},
        alarm_id="entrypoint-alarm",
    )

    class _PluginAlarmDetector(SystemEventsDetector):
        def __init__(self, context):
            super().__init__()
            self.context = context
            self._event = alarm

        def get_name(self):
            return "safety/ppe"

        def get(self):
            event, self._event = self._event, None
            return [event] if event is not None else []

        def put(self, data):
            pass

        def set_params_impl(self):
            pass

        def get_params_impl(self):
            return {}

        def init_impl(self, **kwargs):
            return True

        def reset_impl(self):
            pass

        def release_impl(self):
            self.was_released = True

        def default(self):
            pass

    module_id = "test.safety/ppe-rule"
    spec = ModuleSpec(
        "ppe-rule",
        "event_detector",
        _PluginAlarmDetector,
        execution_modes=("thread",),
        capabilities=("object_handler",),
    )
    plugin_registry.register_plugin(
        PluginSpec("test.safety", PLUGIN_API_VERSION, modules=(spec,))
    )

    class _Pipeline:
        def get_sources(self):
            return []

    class _ObjectsHandler:
        def __init__(self):
            self.subscribers = []

        def subscribe(self, *subscribers):
            self.subscribers.extend(subscribers)

    handler = _ObjectsHandler()
    candidate = EvilEyeBase.create_instance(module_id, EventDetectorContext(objects_handler=handler))
    with pytest.raises(PluginError, match="does not support execution_mode"):
        candidate.set_params(execution_mode="process")

    service = EventsService()
    service.initialize_detectors(
        {"enabled": [module_id], module_id: {"threshold": 0.5}},
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.initialize_controller({})

    controller = service.get_detectors_controller()
    assert controller.flush_once() is True
    snapshot = controller.get()

    assert snapshot["safety/ppe"][0].alarm_id == "entrypoint-alarm"
    detector = service.get_detector(module_id)
    assert detector.context.objects_handler is handler
    assert detector in handler.subscribers

    def fail_get():
        raise RuntimeError("event detector crashed")

    detector.module.get = fail_get
    assert controller.flush_once() is False
    assert detector.get_runtime_stats()["degraded"] is True
    assert "event detector crashed" in detector.get_runtime_stats()["last_error"]
    assert controller.get_runtime_stats()["degraded"] is True
    module = detector.module
    service.release()
    assert module.was_released is True


def test_corrupt_alarm_journal_is_reported_without_overwriting(tmp_path):
    adapter = JsonAdapterAlarmEvents(None)
    adapter.set_params(image_dir=str(tmp_path))
    adapter.init()
    file_path = tmp_path / "Events" / "2026-10-09" / "Metadata" / "alarm_events.json"
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text("{broken", encoding="utf-8")
    alarm = AlarmEvent("ppe_violation", timestamp=datetime(2026, 10, 9, 10, 0, 0), alarm_id="stable-alarm-2")

    with pytest.raises(json.JSONDecodeError):
        adapter.insert(alarm)

    assert file_path.read_text(encoding="utf-8") == "{broken"


def test_event_queue_overflow_and_shutdown_are_diagnosed():
    processor = EventsProcessor([], None)
    processor.queue_maxsize = 1
    from queue import Queue

    processor.queue = Queue(maxsize=1)
    for _ in range(processor.queue_maxsize):
        processor.queue.put_nowait({})

    assert processor.put({"AlarmEvent": []}) is False
    assert processor.get_runtime_stats()["degraded"] is True
    processor.stop()
    assert processor.get_runtime_stats()["degraded"] is True


def test_alarm_adapter_temporarily_failing_write_is_retried():
    class _FlakyAdapter:
        def __init__(self):
            self.calls = 0
            self.saved = []

        def insert(self, event):
            self.calls += 1
            if self.calls == 1:
                raise OSError("temporary storage failure")
            self.saved.append(event.alarm_id)

    alarm = AlarmEvent("ppe_violation", alarm_id="retryable-alarm")
    adapter = _FlakyAdapter()
    processor = EventsProcessor([adapter], None)
    processor.events_adapters = {"AlarmEvent": [adapter]}

    processor._adapter_call(alarm, "insert")

    assert adapter.calls == 2
    assert adapter.saved == ["retryable-alarm"]
    assert processor.get_runtime_stats()["degraded"] is False


class _CollectingAlarmAdapter:
    def __init__(self):
        self.saved = []

    def insert(self, event):
        self.saved.append(event.alarm_id)


def _processor_with_adapter(adapter):
    processor = EventsProcessor([adapter], None)
    processor.events_adapters = {"AlarmEvent": [adapter]}
    return processor


def test_event_processor_drains_accepted_batches_before_stop():
    adapter = _CollectingAlarmAdapter()
    processor = _processor_with_adapter(adapter)
    expected = [f"drain-{index}" for index in range(12)]
    for alarm_id in expected:
        assert processor.put({"AlarmEvent": [AlarmEvent("test", alarm_id=alarm_id)]})

    processor.start()
    processor.stop()

    stats = processor.get_runtime_stats()
    assert adapter.saved == expected
    assert stats["queue_size"] == 0
    assert stats["worker_alive"] is False
    assert stats["degraded"] is False


def test_event_processor_can_restart_after_clean_stop():
    adapter = _CollectingAlarmAdapter()
    processor = _processor_with_adapter(adapter)
    processor.start()
    processor.stop()

    processor.start()
    assert processor.put({"AlarmEvent": [AlarmEvent("test", alarm_id="after-restart")]})
    processor.stop()

    assert adapter.saved == ["after-restart"]
    assert processor.get_runtime_stats()["worker_alive"] is False


def test_event_processor_stop_timeout_is_visible_and_late_put_is_rejected():
    from threading import Event

    started = Event()
    release = Event()

    class _BlockingAdapter(_CollectingAlarmAdapter):
        def insert(self, event):
            started.set()
            assert release.wait(timeout=3)
            super().insert(event)

    adapter = _BlockingAdapter()
    processor = _processor_with_adapter(adapter)
    processor.stop_timeout_secs = 0.05
    assert processor.put({"AlarmEvent": [AlarmEvent("test", alarm_id="blocked")]})
    processor.start()
    assert started.wait(timeout=2)

    processor.stop()
    stats = processor.get_runtime_stats()
    assert stats["worker_alive"] is True
    assert stats["degraded"] is True
    assert "shutdown timed out" in stats["last_error"]
    assert processor.put({"AlarmEvent": [AlarmEvent("test", alarm_id="late")]}) is False

    release.set()
    processor.processing_thread.join(timeout=2)
    assert processor.get_runtime_stats()["worker_alive"] is False
    assert adapter.saved == ["blocked"]


def test_permanent_alarm_adapter_failure_is_reported():
    class _BrokenAdapter:
        def insert(self, event):
            raise OSError("storage unavailable")

    adapter = _BrokenAdapter()
    processor = _processor_with_adapter(adapter)
    processor._adapter_call(AlarmEvent("test", alarm_id="not-saved"), "insert")

    stats = processor.get_runtime_stats()
    assert stats["adapter_failures"] == 1
    assert stats["degraded"] is True
    assert "storage unavailable" in stats["last_error"]


def test_alarm_json_infers_camera_name_before_acl_filtering(tmp_path):
    metadata = tmp_path / "Events" / "2026-10-11" / "Metadata"
    metadata.mkdir(parents=True)
    (metadata / "alarm_events.json").write_text(
        json.dumps(
            [
                {
                    "alarm_id": "source-name-omitted",
                    "ts": "2026-10-11T12:00:00",
                    "alarm_type": "ppe_violation",
                    "severity": "critical",
                    "source_id": 0,
                    "source_name": None,
                    "details": {"rule": "hardhat_required"},
                }
            ]
        ),
        encoding="utf-8",
    )
    source = JsonLabelJournalDataSource(
        str(tmp_path),
        params={
            "pipeline": {
                "sources": [{"source_ids": [0], "source_names": ["Cam0"]}]
            }
        },
    )
    source.set_date("2026-10-11")
    source.begin_request()

    rows = source.fetch(
        page=0,
        size=10,
        filters={"journal_kind": "events", "source_names": ["Cam0"]},
        sort=[],
    )

    assert len(rows) == 1
    assert rows[0]["source_name"] == "Cam0"
