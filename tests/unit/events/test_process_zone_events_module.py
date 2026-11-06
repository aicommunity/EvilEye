from __future__ import annotations

import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import numpy as np

from evileye.controller.services.events_service import EventsService
from evileye.events_detectors.event_zone import ZoneEvent
from evileye.utils import threading_events


class _Track:
    def __init__(self, bbox):
        self.bounding_box = bbox


class _SnapshotObject:
    def __init__(
        self,
        object_id,
        history,
        *,
        bbox=None,
        timestamp=None,
        frame=None,
        time_lost=None,
    ):
        self.object_id = object_id
        self.global_id = object_id
        self.source_id = 0
        self.class_id = 0
        self.history = history
        self.track = _Track(bbox if bbox is not None else history[-1].track.bounding_box)
        self.frame_id = history[-1].frame_id if history else None
        self.time_stamp = timestamp or (history[-1].time_stamp if history else None)
        self.time_detected = history[0].time_stamp if history else self.time_stamp
        self.time_lost = time_lost
        self.last_image = frame
        self.attributes = {}


class _ObjectsHandler:
    def __init__(self):
        self.subscribers = []
        self.active = SimpleNamespace(objects=[])
        self.lost = SimpleNamespace(objects=[])

    def subscribe(self, *subscribers):
        self.subscribers.extend(subscribers)

    def get(self, kind, source_id):
        return getattr(self, kind)

    def notify(self):
        for subscriber in self.subscribers:
            subscriber.update()


class _Pipeline:
    def get_sources(self):
        return [object()]


def _history(object_id, timestamps, *, inside=True):
    rows = []
    for frame_id, timestamp in enumerate(timestamps):
        x1, y1, x2, y2 = (40, 50, 60, 80) if inside or frame_id < 4 else (90, 50, 110, 80)
        rows.append(
            SimpleNamespace(
                object_id=object_id,
                global_id=object_id,
                source_id=0,
                class_id=0,
                frame_id=frame_id,
                time_stamp=timestamp,
                time_detected=timestamps[0],
                time_lost=None,
                track=_Track([x1, y1, x2, y2]),
            )
        )
    return rows


def _frame(frame_id):
    return SimpleNamespace(
        source_id=0,
        frame_id=frame_id,
        time_stamp=datetime.now(),
        current_video_position=None,
        image=np.full((100, 120, 3), frame_id, dtype=np.uint8),
    )


def _wait_events(detector, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events = detector.get()
        if events:
            return events
        time.sleep(0.02)
    return []


def _start_zone_service(handler, *, config=None):
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": ["ZoneEventsDetector"],
            "ZoneEventsDetector": {
                "execution_mode": "process",
                "event_threshold": 2,
                "zone_left_threshold": 1,
                "sources": {
                    "0": [[
                        [0.2, 0.2],
                        [0.8, 0.2],
                        [0.8, 0.9],
                        [0.2, 0.9],
                    ]]
                },
                **(config or {}),
            },
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.start_detectors()
    return service, service.get_detector("ZoneEventsDetector")


def test_builtin_zone_detector_uses_spawn_process_and_emits_enter_and_exit():
    handler = _ObjectsHandler()
    service, detector = _start_zone_service(handler)
    try:
        assert detector.execution_mode == "process"
        assert detector.get_runtime_stats()["worker_running"] is True

        base = datetime.now() - timedelta(seconds=10)
        enter_history = _history(42, [base + timedelta(seconds=i) for i in range(4)])
        handler.active = SimpleNamespace(
            objects=[_SnapshotObject(42, enter_history, frame=_frame(3))]
        )
        handler.notify()
        entered = _wait_events(detector)

        assert len(entered) == 1
        assert isinstance(entered[0], ZoneEvent)
        assert entered[0].finished is False
        assert entered[0].object_id == 42
        assert entered[0].img_entered.image.shape == (100, 120, 3)

        exit_times = [base + timedelta(seconds=i) for i in range(7)]
        exit_history = _history(42, exit_times, inside=False)
        handler.active = SimpleNamespace(
            objects=[
                _SnapshotObject(
                    42,
                    exit_history,
                    bbox=exit_history[-1].track.bounding_box,
                    timestamp=exit_times[-1],
                    frame=_frame(6),
                )
            ]
        )
        handler.notify()
        exited = _wait_events(detector)

        assert len(exited) == 1
        assert exited[0].finished is True
        assert exited[0].object_id == 42
        assert exited[0].img_left.image.shape == (100, 120, 3)
        assert detector.get_runtime_stats()["degraded"] is False
    finally:
        service.release()


def test_zone_commands_from_ui_update_process_worker_and_config():
    handler = _ObjectsHandler()
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": ["ZoneEventsDetector"],
            "ZoneEventsDetector": {
                "execution_mode": "process",
                "sources": {"0": []},
            },
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    detector = service.get_detector("ZoneEventsDetector")
    coords = [[0.1, 0.1], [0.7, 0.1], [0.7, 0.95], [0.1, 0.95]]
    try:
        service.start_detectors()
        threading_events.notify("new zone", 0, coords, "poly")
        assert detector.get_params()["sources"]["0"] == [coords]

        base = datetime.now() - timedelta(seconds=10)
        history = _history(33, [base + timedelta(seconds=i) for i in range(4)])
        handler.active = SimpleNamespace(
            objects=[_SnapshotObject(33, history, frame=_frame(3))]
        )
        handler.notify()
        events = _wait_events(detector)

        assert len(events) == 1
        assert events[0].object_id == 33
        assert events[0].finished is False
        assert detector.get_runtime_stats()["degraded"] is False
    finally:
        service.release()


def test_zone_detector_finishes_active_event_when_object_is_lost():
    handler = _ObjectsHandler()
    service, detector = _start_zone_service(handler)
    try:
        base = datetime.now() - timedelta(seconds=10)
        history = _history(77, [base + timedelta(seconds=i) for i in range(4)])
        handler.active = SimpleNamespace(
            objects=[_SnapshotObject(77, history, frame=_frame(3))]
        )
        handler.notify()
        started = _wait_events(detector)
        assert len(started) == 1
        assert started[0].finished is False

        handler.active = SimpleNamespace(objects=[])
        handler.lost = SimpleNamespace(
            objects=[
                _SnapshotObject(
                    77,
                    history,
                    timestamp=base + timedelta(seconds=5),
                    time_lost=base + timedelta(seconds=5),
                )
            ]
        )
        handler.notify()
        finished = _wait_events(detector)

        assert len(finished) == 1
        assert finished[0].finished is True
        assert finished[0].object_id == 77
        assert finished[0].img_left.image.shape == (100, 120, 3)
        assert detector.get_runtime_stats()["degraded"] is False
    finally:
        service.release()
from datetime import datetime, timedelta
from types import SimpleNamespace

from evileye.events_detectors.zone_events_detector import ZoneEventsDetector


def test_zone_lost_state_is_scoped_by_source_id():
    class _PerSourceHandler:
        def __init__(self):
            self.active = {0: SimpleNamespace(objects=[]), 1: SimpleNamespace(objects=[])}
            self.lost = {0: SimpleNamespace(objects=[]), 1: SimpleNamespace(objects=[])}

        def get(self, kind, source_id):
            return getattr(self, kind)[source_id]

    handler = _PerSourceHandler()
    detector = ZoneEventsDetector(handler)
    zone = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]]
    detector.set_params(
        sources={"0": [zone], "1": [zone]},
        event_threshold=0,
        zone_left_threshold=1,
    )
    detector.init()

    def _obj(source_id, object_id):
        start = datetime.now() - timedelta(seconds=4)
        history = [
            SimpleNamespace(
                source_id=source_id,
                object_id=object_id,
                frame_id=frame_id,
                time_stamp=start + timedelta(seconds=frame_id),
                track=SimpleNamespace(bounding_box=[800, 800, 1000, 1000]),
            )
            for frame_id in range(4)
        ]
        return SimpleNamespace(
            source_id=source_id,
            object_id=object_id,
            frame_id=3,
            time_stamp=history[-1].time_stamp,
            time_lost=history[-1].time_stamp + timedelta(seconds=2),
            track=history[-1].track,
            history=history,
            last_image=None,
        )

    source_zero = _obj(0, 5)
    source_one = _obj(1, 5)
    handler.active[0] = SimpleNamespace(objects=[source_zero])
    handler.active[1] = SimpleNamespace(objects=[source_one])
    try:
        assert len(detector._process_once({0})) == 1
        assert len(detector._process_once({1})) == 1
        assert set(detector.obj_ids_zone) == {(0, 5), (1, 5)}

        handler.active[0] = SimpleNamespace(objects=[])
        handler.lost[0] = SimpleNamespace(objects=[source_zero])
        finished = detector._process_once({0})

        assert len(finished) == 1
        assert finished[0].source_id == 0
        assert set(detector.obj_ids_zone) == {(1, 5)}
    finally:
        detector.release()
def test_zone_process_event_reaches_json_journal_with_evidence(tmp_path):
    import json

    from evileye.database_controller.json_adapter_zone_events import JsonAdapterZoneEvents
    from evileye.events_control.events_processor import EventsProcessor

    handler = _ObjectsHandler()
    service = EventsService()
    service.initialize_detectors(
        {
            "enabled": ["ZoneEventsDetector"],
            "ZoneEventsDetector": {
                "execution_mode": "process",
                "event_threshold": 2,
                "zone_left_threshold": 1,
                "sources": {
                    "0": [[
                        [0.2, 0.2],
                        [0.8, 0.2],
                        [0.8, 0.9],
                        [0.2, 0.9],
                    ]]
                },
            },
        },
        _Pipeline(),
        handler,
        use_database=False,
    )
    service.initialize_controller({})
    detector = service.get_detector("ZoneEventsDetector")
    controller = service.get_detectors_controller()

    adapter = JsonAdapterZoneEvents(None)
    adapter.set_params(image_dir=str(tmp_path))
    adapter.init()
    adapter.start()
    processor = EventsProcessor([adapter], None)
    processor.init()
    processor.start()

    try:
        service.start_detectors()
        base = datetime.now() - timedelta(seconds=10)
        history = _history(91, [base + timedelta(seconds=i) for i in range(4)])
        handler.active = SimpleNamespace(
            objects=[_SnapshotObject(91, history, frame=_frame(3))]
        )
        handler.notify()

        deadline = time.monotonic() + 5.0
        snapshot = {}
        while time.monotonic() < deadline:
            if controller.flush_once():
                snapshot = controller.get()
                break
            time.sleep(0.02)

        assert len(snapshot["ZoneEventsDetector"]) == 1
        assert snapshot["ZoneEventsDetector"][0].object_id == 91
        assert processor.put(snapshot) is True

        path = (
            tmp_path
            / "Events"
            / base.strftime("%Y-%m-%d")
            / "Metadata"
            / "zone_events_entered.json"
        )
        deadline = time.monotonic() + 3.0
        while not path.exists() and time.monotonic() < deadline:
            time.sleep(0.02)
        records = json.loads(path.read_text(encoding="utf-8"))

        assert records[0]["source_id"] == 0
        assert records[0]["object_id"] == 91
        assert records[0]["frame_path"]
        assert (tmp_path / records[0]["frame_path"]).is_file()
    finally:
        processor.stop()
        adapter.stop()
        service.release()
def test_events_processor_persists_source_less_long_term_events():
    from evileye.events_control.events_processor import EventsProcessor

    class _LongTermEvent:
        source_id = None
        timestamp = datetime.now()

        def __init__(self):
            self.event_id = None

        def set_id(self, event_id):
            self.event_id = event_id

        def get_name(self):
            return "SourceLessLongTermEvent"

        def is_long_term(self):
            return True

        def is_finished(self):
            return False

    class _Adapter:
        def __init__(self):
            self.events = []

        def get_event_name(self):
            return "SourceLessLongTermEvent"

        def insert(self, event):
            self.events.append(event)

    adapter = _Adapter()
    processor = EventsProcessor([adapter], None)
    processor.init()
    callback_calls = []
    processor.set_event_recording_callback(lambda *args: callback_calls.append(args))
    processor.start()
    try:
        event = _LongTermEvent()
        assert processor.put({"SourceLessLongTermEvent": [event]}) is True

        deadline = time.monotonic() + 2.0
        while not adapter.events and time.monotonic() < deadline:
            time.sleep(0.01)

        assert adapter.events == [event]
        assert callback_calls == []
    finally:
        processor.stop()
