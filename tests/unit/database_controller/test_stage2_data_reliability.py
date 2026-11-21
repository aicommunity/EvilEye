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
        import psycopg2

        spool = PgSpool(tmp_path)
        spool.append({"n": "first"})
        spool.append({"n": "second"})

        def failing(item):
            if item["n"] == "first":
                raise psycopg2.OperationalError("db still down")

        assert spool.replay(failing) == 0
        assert spool.pending_count() == 2

    def test_replay_quarantines_corrupt_entries(self, tmp_path):
        spool = PgSpool(tmp_path)
        spool.append({"n": "good"})
        corrupt = spool.root / "0-corrupt.json"
        corrupt.write_text("not-json", encoding="utf-8")
        processed = []
        assert spool.replay(processed.append) == 1
        assert processed == [{"n": "good"}]
        assert spool.pending_count() == 0
        assert any(spool.quarantine.iterdir())

    def test_budget_rejects_oversized_record(self, tmp_path):
        spool = PgSpool(tmp_path, max_bytes=1)
        assert spool.append({"n": "big-item"}) is False
        assert spool.pending_count() == 0
        assert spool.last_reject == "budget"

    def test_non_dict_record_returns_false(self, tmp_path):
        spool = PgSpool(tmp_path)
        assert spool.append("not-a-record") is False
        assert spool.pending_count() == 0

    def test_namespaces_do_not_share_files(self, tmp_path):
        left = PgSpool(tmp_path, namespace="ZoneEvent")
        right = PgSpool(tmp_path, namespace="AlarmEvent")
        assert left.append({"n": 1})
        assert right.pending_count() == 0
        assert left.pending_count() == 1

    def test_legacy_pickle_is_quarantined_not_loaded(self, tmp_path):
        spool = PgSpool(tmp_path)
        (spool.root).mkdir(parents=True, exist_ok=True)
        (spool.root / "1.pkl").write_bytes(b"pickle-bytes")
        processed = []
        assert spool.replay(processed.append) == 0
        assert processed == []
        assert spool.pending_count() == 0
        assert list(spool.quarantine.glob("*.pkl"))


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
        assert len(calls["spool"]) == 1
        record = calls["spool"][0]
        assert record["kind"] == "deferred"
        assert record["op"] == "update"
        assert record["fields"] == {"id": 2}
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


class TestZoneSpoolRoundtrip:
    def test_zone_coords_survive_deferred_spool(self, tmp_path):
        from evileye.database_controller.db_adapter import DatabaseAdapterBase
        from evileye.events_detectors.event_zone import ZoneEvent
        from evileye.events_detectors.zone import Zone

        class _Controller:
            def get_params(self):
                return {"image_dir": str(tmp_path)}

            def get_cameras_params(self):
                return {}

            def is_connected(self):
                return True

        class _Adapter(DatabaseAdapterBase):
            def _process_queue_item(self, item):
                return None

            def _insert_impl(self, data):
                return None

            def _update_impl(self, data):
                return None

        adapter = _Adapter(_Controller())
        adapter.event_name = "ZoneEvent"
        event = object.__new__(ZoneEvent)
        event.zone = Zone(1, ((0.1, 0.2), (0.3, 0.4)), "rect", True)
        event.source_id = 1
        event.object_id = 7
        record = adapter._deferred_spool_record("update", event)
        restored = adapter._event_from_spool_record(record)
        assert list(restored.zone.get_coords()) == [[0.1, 0.2], [0.3, 0.4]]
        assert restored.source_id == 1


class TestConfigHistoryQueryFailure:
    def test_failed_query_is_not_an_empty_history(self):
        import logging

        from evileye.database.config_history_manager import ConfigHistoryManager

        manager = ConfigHistoryManager.__new__(ConfigHistoryManager)
        manager.logger = logging.getLogger("test.config_history")

        class _Db:
            def query(self, *_args, **_kwargs):
                return None

        manager.db_controller = _Db()
        try:
            manager.get_config_history()
        except RuntimeError as exc:
            assert "database query failed" in str(exc)
        else:
            raise AssertionError("failed query was returned as an empty history")


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

    def test_missing_pool_does_not_return_zero(self):
        from evileye.database_controller.database_controller_pg import DatabaseControllerPg

        controller = DatabaseControllerPg.__new__(DatabaseControllerPg)
        controller.conn_pool = None
        assert controller.get_next_event_id(["zone_events"]) is None

    def test_retention_predicates_match_real_columns(self):
        from evileye.database_controller.database_controller_pg import RETENTION_PREDICATES

        assert "time_entered" in RETENTION_PREDICATES["zone_events"]
        assert "time_stamp" not in RETENTION_PREDICATES["zone_events"]
        assert "camera_events" in RETENTION_PREDICATES
        assert "cam_events" not in RETENTION_PREDICATES
        assert "alarm_events" in RETENTION_PREDICATES
