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

    with pytest.raises(
        PluginError, match="event_updates, source_updates or event_commands"
    ):
        adapter.set_params(execution_mode="process")


def test_events_service_process_alarm_reaches_json_journal(tmp_path, monkeypatch):
    from evileye.controller.services.events_service import EventsService
    from evileye.database_controller.json_adapter_alarm_events import JsonAdapterAlarmEvents
    from evileye.events_control.events_processor import EventsProcessor
    from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource
    from evileye.api.core.journal_grouping import group_events_rows
    from fastapi.testclient import TestClient
    from evileye.api.app import create_app
    from evileye.api.security import hash_password
    from evileye.api.core import journal_service

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
    _register_module()
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
    client = None
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

        source = JsonLabelJournalDataSource(
            str(tmp_path),
            params={
                "pipeline": {
                    "sources": [
                        {"source_ids": [0], "source_names": ["Cam0"]}
                    ]
                }
            },
        )
        row = source._map_item(records[0], "alarm", "2026-10-11", 0)
        assert row["source_name"] == "Cam0"
        source.set_date("2026-10-11")
        source.begin_request()
        assert source.get_total(
            {"journal_kind": "events", "source_names": ["Cam0"]}
        ) == 1
        assert group_events_rows([row])[0]["event"] == "ppe_violation"

        config_path = tmp_path / "journal-config.json"
        config_path.write_text(
            json.dumps(
                {
                    "controller": {
                        "use_database": False,
                        "image_dir": str(tmp_path),
                    },
                    "pipeline": {
                        "sources": [
                            {"source_ids": [0], "source_names": ["Cam0"]}
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        (tmp_path / "credentials.json").write_text(
            json.dumps(
                {
                    "web_auth": {
                        "enabled": True,
                        "session_secret": "unit-test-session-secret-long-enough",
                        "internal_token": "unit-test-internal-token",
                        "users": [
                            {
                                "username": "test",
                                "password_hash": hash_password("test-user-password"),
                                "role": "user",
                                "allowed_cameras": ["Cam0"],
                            }
                        ],
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("EVILEYE_SITE_DIR", str(tmp_path))
        monkeypatch.setattr(
            journal_service,
            "get_current_config_path",
            lambda: str(config_path),
        )
        for name, value in {
            "_runtime_params_cache": None,
            "_light_config_path_cache": None,
            "_image_base_dir_cache": None,
            "_json_source_cache": {},
            "_grouped_row_cache": {"events": {}, "objects": {}},
            "_filters_meta_cache": None,
            "_journal_stats_page_cache": {},
            "_path_resolve_cache": {},
        }.items():
            monkeypatch.setattr(journal_service, name, value)

        client = TestClient(create_app())
        login = client.post(
            "/api/v1/auth/login",
            json={"username": "test", "password": "test-user-password"},
        )
        assert login.status_code == 200
        response = client.get(
            "/api/v1/journals/events/grouped",
            params={"page": 0, "size": 10, "date": "2026-10-11"},
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["available"] is True
        alarm_rows = [
            item
            for item in payload["items"]
            if item.get("event") == "ppe_violation"
        ]
        assert len(alarm_rows) == 1
        alarm_row = alarm_rows[0]
        assert alarm_row["source"] == "Cam0"
        assert "critical" in alarm_row["information"]
        assert "from_service" in alarm_row["information"]
        assert alarm_row["time"].startswith("2026-10-11T12:00:00")
    finally:
        if client is not None:
            client.close()
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


def test_builtin_camera_events_detector_uses_source_update_contract():
    from evileye.controller.services.events_service import EventsService

    class _Source:
        def __init__(self):
            self.subscribers = []
            self.disconnects = []
            self.reconnects = []

        def subscribe(self, *subscribers):
            self.subscribers.extend(subscribers)

        def get_disconnects_info(self):
            values, self.disconnects = self.disconnects, []
            return values

        def get_reconnects_info(self):
            values, self.reconnects = self.reconnects, []
            return values

        def disconnect(self, address, timestamp):
            self.disconnects.append((address, timestamp, False))
            for subscriber in self.subscribers:
                subscriber.update()

    class _Pipeline:
        def __init__(self, source):
            self.source = source

        def get_sources(self):
            return [self.source]

    class _ObjectsHandler:
        def subscribe(self, *subscribers):
            pass

    source = _Source()
    service = EventsService()
    service.initialize_detectors(
        {"enabled": ["CamEventsDetector"]},
        _Pipeline(source),
        _ObjectsHandler(),
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector("CamEventsDetector")
    assert detector.execution_mode == "process"
    assert source.subscribers == [detector]

    source.disconnect("rtsp://camera-1/stream", datetime(2026, 10, 11, 13, 0, 0))
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

        events = snapshot["CamEventsDetector"]
        assert len(events) == 1
        assert events[0].camera_address == "rtsp://camera-1/stream"
        assert events[0].con_status is False
        assert events[0].timestamp == datetime(2026, 10, 11, 13, 0, 0)
    finally:
        service.release()


def test_capture_source_connection_transitions_notify_subscribers():
    from threading import RLock

    from evileye.capture.video_capture_base import VideoCaptureBase

    class _ConcreteVideoCapture(VideoCaptureBase):
        def get_frames_impl(self):
            return []

        def _grab_frames(self):
            return None

        def _retrieve_frames(self):
            return None

        def init_impl(self):
            return None

        def release_impl(self):
            return None

        def reset_impl(self):
            return None

        def default(self):
            return None

    class _Subscriber:
        def __init__(self):
            self.updates = 0

        def update(self):
            self.updates += 1

    source = object.__new__(_ConcreteVideoCapture)
    source.conn_mutex = RLock()
    source.disconnects = []
    source.reconnects = []
    source._disconnect_count = 0
    source._reconnect_count = 0
    source._last_connection_transition = None
    source.subscribers = [_Subscriber()]
    source.is_working = False
    source._camera_event_identity = lambda: "camera-1"
    timestamp = datetime(2026, 10, 11, 13, 0, 0)

    source._record_disconnect(timestamp)
    source._record_reconnect(timestamp)

    assert source.subscribers[0].updates == 2
    assert source.get_disconnects_info() == [("camera-1", timestamp, False)]
    assert source.get_reconnects_info() == [("camera-1", timestamp, False)]


@pytest.mark.parametrize(
    "detector_id",
    ("ScheduleAlarmEventsDetector", "FieldOfViewEventsDetector"),
)
def test_builtin_schedule_alarm_detector_uses_object_update_process_contract(detector_id):
    from evileye.controller.services.events_service import EventsService
    from evileye.events_detectors.event_schedule_alarm import ScheduleAlarmEvent
    from evileye.events_detectors.event_registry import register_builtins

    register_builtins()

    class _Pipeline:
        def get_sources(self):
            return [object()]

    history_timestamp = datetime.now().replace(microsecond=0)

    class _ObjectsHandler:
        def __init__(self):
            now = history_timestamp
            self.subscribers = []
            history = SimpleNamespace(
                object_id=42,
                global_id=8,
                source_id=0,
                class_id=2,
                frame_id=17,
                time_stamp=now,
                time_detected=now,
                time_lost=None,
            )
            self.active = SimpleNamespace(
                objects=[
                    SimpleNamespace(
                        object_id=42,
                        global_id=8,
                        source_id=0,
                        class_id=2,
                        frame_id=17,
                        time_stamp=now,
                        time_detected=now,
                        time_lost=None,
                        track=SimpleNamespace(bounding_box=[1.0, 2.0, 3.0, 4.0]),
                        attributes={},
                        history=[history],
                    )
                ]
            )
            self.lost = SimpleNamespace(objects=[])

        def subscribe(self, *subscribers):
            self.subscribers.extend(subscribers)

        def get(self, kind, source_id):
            return getattr(self, kind)

        def notify(self):
            for subscriber in self.subscribers:
                subscriber.update()

    handler = _ObjectsHandler()
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": [detector_id],
            detector_id: {
                "default_schedule": {
                    "enabled": True,
                    "weekdays": list(range(7)),
                    "periods": [["00:00:00", "23:59:59"]],
                    "class_ids": [2],
                }
            },
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector(detector_id)
    assert detector.module_id == f"evileye/{detector_id}"
    assert detector.execution_mode == "process"
    assert handler.subscribers == [detector]
    service.start_detectors()
    handler.notify()
    controller = service.get_detectors_controller()

    try:
        deadline = time.monotonic() + 5.0
        events = []
        while time.monotonic() < deadline:
            controller.flush_once()
            events = controller.get().get(detector_id, [])
            if events:
                break
            time.sleep(0.02)

        assert len(events) == 1
        assert isinstance(events[0], ScheduleAlarmEvent)
        assert events[0].source_id == 0
        assert events[0].object_id == 42
        assert events[0].finished is False
        assert events[0].time_obj_detected == history_timestamp

        lost_timestamp = datetime.now().replace(microsecond=0)
        lost_object = handler.active.objects[0]
        lost_object.time_lost = lost_timestamp
        handler.active = SimpleNamespace(objects=[])
        handler.lost = SimpleNamespace(objects=[lost_object])
        handler.notify()

        finished_events = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            controller.flush_once()
            finished_events = controller.get().get(detector_id, [])
            if finished_events:
                break
            time.sleep(0.02)

        assert len(finished_events) == 1
        assert finished_events[0].finished is True
        assert finished_events[0].object_id == 42
        assert finished_events[0].time_lost == lost_timestamp
    finally:
        service.release()


def test_builtin_attribute_events_detector_transports_evidence_frames_in_process():
    import numpy as np

    from evileye.controller.services.events_service import EventsService
    from evileye.events_detectors.event_attribute import AttributeEvent
    from evileye.events_detectors.event_registry import register_builtins
    from evileye.core.contracts import EventFrameSnapshot
    from evileye.core.frame import CaptureImage

    register_builtins()

    class _Pipeline:
        def get_sources(self):
            return [object()]

    class _ObjectsHandler:
        def __init__(self):
            self.subscribers = []
            self.timestamp = datetime.now().replace(microsecond=0)
            self.obj = SimpleNamespace(
                object_id=51,
                global_id=9,
                source_id=0,
                class_id=2,
                frame_id=10,
                time_stamp=self.timestamp,
                time_detected=self.timestamp,
                time_lost=None,
                track=SimpleNamespace(bounding_box=[1.0, 2.0, 8.0, 9.0]),
                attributes={"hardhat": {"state": "exists"}},
                history=[],
                last_image=self._frame(10),
            )
            self.active = SimpleNamespace(objects=[self.obj])
            self.lost = SimpleNamespace(objects=[])

        @staticmethod
        def _frame(frame_id):
            frame = CaptureImage()
            frame.source_id = 0
            frame.frame_id = frame_id
            frame.time_stamp = datetime.now().timestamp()
            frame.image = np.full((12, 16, 3), 80 + frame_id, dtype=np.uint8)
            return frame

        def subscribe(self, *subscribers):
            self.subscribers.extend(subscribers)

        def get(self, kind, source_id):
            return getattr(self, kind)

        def notify(self):
            for subscriber in self.subscribers:
                subscriber.update()

    handler = _ObjectsHandler()
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": ["AttributeEventsDetector"],
            "AttributeEventsDetector": {
                "sources": {"0": {"hardhat_ok": ["hardhat"]}},
            },
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector("AttributeEventsDetector")
    assert detector.execution_mode == "process"
    assert "event_frames" in detector.registered_module.spec.capabilities
    assert handler.subscribers == [detector]
    service.start_detectors()
    handler.notify()
    controller = service.get_detectors_controller()

    try:
        deadline = time.monotonic() + 5.0
        events = []
        while time.monotonic() < deadline:
            controller.flush_once()
            events = controller.get().get("AttributeEventsDetector", [])
            if events:
                break
            time.sleep(0.02)

        assert len(events) == 1
        assert isinstance(events[0], AttributeEvent)
        assert events[0].matched_event_name == "hardhat_ok"
        assert events[0].matched_attrs == ["hardhat"]
        assert isinstance(events[0].img_found, EventFrameSnapshot)
        assert events[0].img_found.image.shape == (12, 16, 3)
        assert events[0].img_found.frame_id == 10

        finish_timestamp = datetime.now().replace(microsecond=0)
        handler.obj.time_lost = finish_timestamp
        handler.obj.last_image = handler._frame(11)
        handler.active = SimpleNamespace(objects=[])
        handler.lost = SimpleNamespace(objects=[handler.obj])
        handler.notify()

        finished_events = []
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            controller.flush_once()
            finished_events = controller.get().get("AttributeEventsDetector", [])
            if finished_events:
                break
            time.sleep(0.02)

        assert len(finished_events) == 1
        assert finished_events[0].finished is True
        assert isinstance(finished_events[0].img_finished, EventFrameSnapshot)
        assert finished_events[0].img_finished.image.shape == (12, 16, 3)
        assert finished_events[0].img_finished.frame_id == 11
        assert finished_events[0].time_finished == finish_timestamp
    finally:
        service.release()


def test_event_update_frame_attachments_have_strict_size_limits():
    from evileye.core.contracts import EventFrameSnapshot

    with pytest.raises(ValueError, match="frame limit"):
        EventFrameSnapshot(
            source_id=0,
            frame_id=1,
            timestamp=0.0,
            current_video_position=None,
            jpeg_bytes=b"x" * (EventFrameSnapshot.MAX_BYTES + 1),
        )

    frame_bytes = b"x" * EventFrameSnapshot.MAX_BYTES
    frames = tuple(
        EventFrameSnapshot(
            source_id=0,
            frame_id=index,
            timestamp=0.0,
            current_video_position=None,
            jpeg_bytes=frame_bytes,
        )
        for index in (1, 2, 3)
    )
    with pytest.raises(ValueError, match="frame attachments exceed"):
        EventUpdate(
            sequence=0,
            kind="object_snapshot",
            source_id=0,
            payload={},
            frames=frames,
        )

def test_process_event_worker_exit_during_shutdown_is_not_reported_as_failure():
    detector = EventDetectorModuleAdapter(_register_module(), EventDetectorContext())
    detector.execution_mode = "process"
    detector._started = True
    detector._closing = True
    detector._mp_control = SimpleNamespace(
        processes=[SimpleNamespace(exitcode=0)]
    )

    detector._check_process_health()

    assert detector.degraded is False
    assert detector.last_error is None



def test_process_detector_failure_does_not_block_healthy_sibling():
    from evileye.events_control.events_controller import EventsDetectorsController

    plugin_id = "tests.process_event_isolation"
    if plugin_registry.get_module(f"{plugin_id}/broken") is None:
        plugin_registry.register_plugin(
            PluginSpec(
                plugin_id,
                PLUGIN_API_VERSION,
                modules=tuple(
                    ModuleSpec(
                        module_id=module_id,
                        kind="event_detector",
                        factory=make_process_event_module,
                        execution_modes=("process",),
                        capabilities=("event_updates",),
                        config_schema=_validate_process_event_config,
                        default_execution_mode="process",
                    )
                    for module_id in ("broken", "healthy")
                ),
            )
        )

    broken = EventDetectorModuleAdapter(
        plugin_registry.get_module(f"{plugin_id}/broken"),
        EventDetectorContext(),
    )
    healthy = EventDetectorModuleAdapter(
        plugin_registry.get_module(f"{plugin_id}/healthy"),
        EventDetectorContext(),
    )
    detectors = (broken, healthy)
    for detector, fail, rule in (
        (broken, True, "broken_rule"),
        (healthy, False, "healthy_rule"),
    ):
        detector.set_params(
            execution_mode="process",
            fail=fail,
            rule=rule,
        )
        assert detector.init() is True
        detector.start()

    controller = EventsDetectorsController(list(detectors))
    controller.init()
    update = EventUpdate(
        sequence=1,
        kind="object_snapshot",
        source_id=5,
        timestamp="2026-10-12T00:00:00Z",
        payload={"active": [], "lost": []},
    )
    try:
        for detector in detectors:
            detector.put(update)

        deadline = time.monotonic() + 5.0
        snapshot = {}
        while time.monotonic() < deadline:
            controller.flush_once()
            snapshot = controller.get()
            if snapshot.get("healthy"):
                break
            time.sleep(0.02)

        healthy_events = snapshot.get("healthy", [])
        assert len(healthy_events) == 1
        assert healthy_events[0].details["rule"] == "healthy_rule"
        assert broken.get_runtime_stats()["degraded"] is True
        controller_stats = controller.get_runtime_stats()
        assert controller_stats["degraded"] is True
        assert "broken" in " ".join(controller_stats["detector_failures"])
        debug_info = {}
        controller.insert_debug_info_by_id(debug_info)
        assert debug_info[controller.id]["runtime"]["degraded"] is True
        assert healthy.get_runtime_stats()["degraded"] is False
    finally:
        controller.stop()
        for detector in detectors:
            detector.stop()
