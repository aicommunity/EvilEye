from threading import Event

import psycopg2
import pytest
from psycopg2 import sql
from psycopg2.extras import Json

from evileye.database_controller.db_adapter_alarm_events import DatabaseAdapterAlarmEvents
from evileye.events_detectors.alarm_event import AlarmEvent
from evileye.events_control.events_processor import EventsProcessor


class _FakeDatabase:
    def __init__(self, *, connected=True, failures=0):
        self.connected = connected
        self.failures = failures
        self.params = {"image_dir": "."}
        self.cameras = []
        self.queries = []
        self.saved = Event()
        self.worker_entered = Event()
        self.allow_query = Event()
        self.block_query = False

    def get_params(self):
        return self.params

    def get_cameras_params(self):
        return self.cameras

    def get_project_id(self):
        return 11

    def get_job_id(self):
        return 23

    def is_connected(self):
        return self.connected

    def query_checked(self, query, values):
        if self.block_query:
            self.worker_entered.set()
            self.allow_query.wait(timeout=2)
        if self.failures:
            self.failures -= 1
            raise psycopg2.OperationalError("temporary database outage")
        self.queries.append((query, values))
        self.saved.set()


def _make_adapter(db):
    adapter = DatabaseAdapterAlarmEvents(db)
    adapter.set_params(table_name="alarm_events", queue_maxsize=4)
    adapter.init()
    return adapter


def test_alarm_database_adapter_retries_and_drains_before_stop():
    db = _FakeDatabase(failures=1)
    adapter = _make_adapter(db)
    alarm = AlarmEvent(
        "ppe_violation",
        severity="critical",
        source_id=7,
        source_name="camera-7",
        details={"rule": "hardhat_required"},
        alarm_id="stable-db-alarm",
    )
    alarm.set_id(42)

    adapter.start()
    adapter.insert(alarm)
    adapter.stop()

    assert db.saved.is_set()
    assert len(db.queries) == 1
    query, values = db.queries[0]
    assert isinstance(query, sql.Composed)
    assert "ON CONFLICT (alarm_id) DO NOTHING" in query._wrapped[-1]._wrapped
    assert values[:7] == [
        42,
        "stable-db-alarm",
        alarm.timestamp,
        "ppe_violation",
        "critical",
        7,
        "camera-7",
    ]
    assert isinstance(values[7], Json)
    assert values[7].adapted == {"rule": "hardhat_required"}
    assert values[8:] == [11, 23]
    assert adapter.get_runtime_stats()["processed_items"] == 1
    assert adapter.get_runtime_stats()["queue_failures"] == 0
    assert adapter.get_runtime_stats()["worker_alive"] is False


def test_alarm_database_adapter_rejects_disconnected_writes_explicitly():
    adapter = _make_adapter(_FakeDatabase(connected=False))
    alarm = AlarmEvent("ppe_violation", alarm_id="offline-db-alarm")

    with pytest.raises(ConnectionError, match="is disconnected"):
        adapter.insert(alarm)

    stats = adapter.get_runtime_stats()
    assert stats["degraded"] is True
    assert stats["queue_failures"] == 1
    assert "disconnected" in stats["last_error"]
    processor_stats = EventsProcessor([adapter], None).get_runtime_stats()
    assert processor_stats["degraded"] is True
    assert processor_stats["adapters"][0]["queue_failures"] == 1


def test_postgres_checked_query_retries_operational_failure():
    import logging

    from evileye.database_controller.database_controller_pg import DatabaseControllerPg
    from evileye.database_controller.database_error_handler import DatabaseErrorHandler

    class _Cursor:
        def __init__(self, pool):
            self.pool = pool

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def execute(self, query, values):
            self.pool.attempts += 1
            if self.pool.attempts == 1:
                raise psycopg2.OperationalError("connection reset")

        def fetchall(self):
            return [(1,)]

    class _Connection:
        def __init__(self, pool):
            self.pool = pool

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def cursor(self):
            return _Cursor(self.pool)

    class _Pool:
        def __init__(self):
            self.attempts = 0
            self.returned = 0

        def getconn(self):
            return _Connection(self)

        def putconn(self, connection):
            self.returned += 1

    pool = _Pool()
    database = object.__new__(DatabaseControllerPg)
    database.conn_pool = pool
    database.error_handler = DatabaseErrorHandler(logging.getLogger("test-postgres-query"))

    assert database.query_checked("SELECT 1", None) == [(1,)]
    assert pool.attempts == 2
    assert pool.returned == 2


def test_postgres_checked_query_raises_when_pool_is_unavailable():
    from evileye.database_controller.database_controller_pg import DatabaseControllerPg
    from evileye.database_controller.database_error_handler import DatabaseErrorHandler

    database = object.__new__(DatabaseControllerPg)
    database.conn_pool = None
    database.error_handler = DatabaseErrorHandler()

    with pytest.raises(psycopg2.OperationalError, match="pool is unavailable"):
        database.query_checked("SELECT 1", None)


def test_alarm_database_adapter_reports_queue_overflow():
    db = _FakeDatabase()
    db.block_query = True
    adapter = _make_adapter(db)
    adapter.set_params(table_name="alarm_events", queue_maxsize=1)

    adapter.start()
    adapter.insert(AlarmEvent("ppe_violation", alarm_id="processing-alarm"))
    assert db.worker_entered.wait(timeout=1)
    adapter.insert(AlarmEvent("ppe_violation", alarm_id="queued-alarm"))
    try:
        with pytest.raises(RuntimeError, match="queue is full"):
            adapter.insert(AlarmEvent("ppe_violation", alarm_id="overflow-alarm"))
    finally:
        db.allow_query.set()
        adapter.stop()

    stats = adapter.get_runtime_stats()
    assert stats["queue_size"] == 0
    assert stats["queue_failures"] == 1
    assert stats["degraded"] is True
