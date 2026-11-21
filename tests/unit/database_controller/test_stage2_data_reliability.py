"""Stage-2 audit fixes: pg spool, adapter filtering, alarm frames, id fallback."""

from __future__ import annotations

import json
from pathlib import Path

from evileye.database_controller.pg_spool import PgSpool
from evileye.events_detectors.event_schedule_alarm import ScheduleAlarmEvent


class _Frame:
    def __init__(self, image):
        self.image = image


class _HistObj:
    def __init__(self, image):
        self.source_id = 0
        self.object_id = 42
        self.class_id = 1
        self.time_detected = "2026-11-21 10:00:00"
        self.time_lost = None
        self.last_image = _Frame(image)


class TestPgSpool:
    def test_append_and_replay_roundtrip(self, tmp_path):
        spool = PgSpool(tmp_path)
        processed = []
        assert spool.append({"a": 1})
        assert spool.append({"b": 2})
        assert spool.pending_count() == 2

        replayed = spool.replay(processed.append)
        assert replayed == 2
        assert processed == [{"a": 1}, {"b": 2}]  # oldest first
        assert spool.pending_count() == 0

    def test_replay_stops_on_failure_and_keeps_items(self, tmp_path):
        spool = PgSpool(tmp_path)
        spool.append("first")
        spool.append("second")

        def failing(item):
            if item == "first":
                raise RuntimeError("db still down")

        assert spool.replay(failing) == 0
        assert spool.pending_count() == 2  # nothing lost

    def test_replay_drops_corrupt_entries(self, tmp_path):
        spool = PgSpool(tmp_path)
        spool.append("good")
        # Plant a corrupt file that sorts before the good one.
        corrupt = spool.root / "0.pkl"
        corrupt.write_bytes(b"not-a-pickle")
        processed = []
        assert spool.replay(processed.append) == 1
        assert processed == ["good"]
        assert spool.pending_count() == 0

    def test_budget_drops_oldest(self, tmp_path):
        spool = PgSpool(tmp_path, max_bytes=1)
        spool.append("big-item-1" * 100)
        spool.append("big-item-2" * 100)
        assert spool.pending_count() <= 1

    def test_unpicklable_item_returns_false(self, tmp_path):
        spool = PgSpool(tmp_path)

        class Bad:
            def __getstate__(self):
                raise TypeError("nope")

        assert spool.append(Bad()) is False
        assert spool.pending_count() == 0


class TestAdapterBackendFilter:
    def test_events_tables_excludes_json_adapters(self):
        import os

        from evileye.database_controller.json_adapter_zone_events import (
            JsonAdapterZoneEvents,
        )
        from evileye.events_control.events_processor import EventsProcessor

        adapter = JsonAdapterZoneEvents(db_controller=None)
        adapter.set_params(image_dir=os.getcwd())
        # storage_backend marker distinguishes journal adapters (audit D2).
        assert adapter.storage_backend == "json"
        assert adapter.get_table_name() == "zone_events_json"

        processor = EventsProcessor.__new__(EventsProcessor)
        processor.db_adapters = [adapter]
        processor.events_adapters = {}
        processor.events_tables = {}
        # Re-run the constructor fragment that builds events_tables.
        for a in processor.db_adapters:
            if getattr(a, "storage_backend", "postgres") != "postgres":
                continue
            event_name = a.get_event_name()
            if event_name not in processor.events_tables and hasattr(a, "get_table_name"):
                processor.events_tables[event_name] = a.get_table_name()
        assert processor.events_tables == {}


class TestScheduleAlarmFrames:
    def _hist(self):
        import numpy as np

        return _HistObj(np.zeros((32, 32, 3), dtype=np.uint8))

    def test_start_event_carries_detected_image(self):
        event = ScheduleAlarmEvent("2026-11-21 10:00:00", "Alarm", self._hist())
        assert event.img_detected is not None
        assert event.img_detected.image is not None
        assert event.img_lost is None

    def test_finished_event_carries_lost_image(self):
        event = ScheduleAlarmEvent(
            "2026-11-21 10:05:00", "Alarm", self._hist(), is_finished=True
        )
        assert event.img_lost is not None
        assert event.img_detected is None

    def test_update_on_finished_propagates_lost_image(self):
        long_term = ScheduleAlarmEvent("2026-11-21 10:00:00", "Alarm", self._hist())
        finished = ScheduleAlarmEvent(
            "2026-11-21 10:05:00", "Alarm", self._hist(), is_finished=True
        )
        long_term.update_on_finished(finished)
        assert long_term.img_lost is finished.img_lost

    def test_no_image_available_stays_none(self):
        hist = self._hist()
        hist.last_image = None
        event = ScheduleAlarmEvent("2026-11-21 10:00:00", "Alarm", hist)
        assert event.img_detected is None


class TestAdapterUpdatePath:
    def _adapter(self, *, connected: bool, backend: str, tmp_path):
        from evileye.database_controller.db_adapter import DatabaseAdapterBase

        calls = {"update": [], "insert": [], "spool": []}

        class _Controller:
            def get_params(self):
                return {"image_dir": str(tmp_path)}

            def get_cameras_params(self):
                return {}

            def is_connected(self):
                return connected

        class _Adapter(DatabaseAdapterBase):
            storage_backend = backend

            def _process_queue_item(self, item):
                return None

            def _insert_impl(self, data):
                calls["insert"].append(data)

            def _update_impl(self, data):
                calls["update"].append(data)

        adapter = _Adapter(_Controller())
        adapter.event_name = "ZoneEvent"
        original = adapter._ensure_spool

        def _spool():
            spool = original()
            if spool is None:
                return None
            real_append = spool.append

            def _append(item):
                calls["spool"].append(item)
                return real_append(item)

            spool.append = _append
            return spool

        adapter._ensure_spool = _spool
        return adapter, calls

    def test_update_calls_impl_when_connected(self, tmp_path):
        adapter, calls = self._adapter(connected=True, backend="postgres", tmp_path=tmp_path)
        adapter.update({"id": 1})
        assert calls["update"] == [{"id": 1}]
        assert calls["spool"] == []

    def test_update_spools_when_postgres_down(self, tmp_path):
        adapter, calls = self._adapter(connected=False, backend="postgres", tmp_path=tmp_path)
        adapter.update({"id": 2})
        assert calls["update"] == []
        assert calls["spool"] == [("deferred", "update", {"id": 2})]
        assert adapter._spooled_items == 1

    def test_json_update_ignores_postgres_outage(self, tmp_path):
        adapter, calls = self._adapter(connected=False, backend="json", tmp_path=tmp_path)
        adapter.update({"id": 3})
        assert calls["update"] == [{"id": 3}]
        assert calls["spool"] == []

    def test_json_insert_ignores_postgres_outage(self, tmp_path):
        adapter, calls = self._adapter(connected=False, backend="json", tmp_path=tmp_path)
        adapter.insert({"id": 4})
        assert calls["insert"] == [{"id": 4}]
        assert calls["spool"] == []


class TestGetNextEventIdFallback:
    def test_get_last_id_epoch_fallback_when_db_unreadable(self, monkeypatch):
        import time as time_module

        from evileye.events_control.events_processor import EventsProcessor

        processor = EventsProcessor.__new__(EventsProcessor)
        processor.events_tables = {"ZoneEvent": "zone_events"}
        processor.long_term_events = {}
        processor.degraded = False
        processor.last_error = None
        processor.logger = __import__("logging").getLogger("test")

        class _BrokenController:
            def get_next_event_id(self, table_names):
                return None

        processor.db_controller = _BrokenController()
        before = int(time_module.time())
        fallback = processor.get_last_id()
        after = int(time_module.time())
        assert before <= fallback <= after
        assert processor.degraded is True
