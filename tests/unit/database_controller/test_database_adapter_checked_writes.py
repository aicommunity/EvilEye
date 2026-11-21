
import psycopg2
import pytest
from psycopg2 import sql

from evileye.database_controller.constants import QueryType
from evileye.database_controller.db_adapter import DatabaseAdapterBase
from evileye.database_controller.db_adapter_attribute_events import DatabaseAdapterAttributeEvents
from evileye.database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from evileye.database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from evileye.database_controller.db_adapter_objects import DatabaseAdapterObjects
from evileye.database_controller.db_adapter_system_events import DatabaseAdapterSystemEvents
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents


class _Database:
    def __init__(self):
        self.params = {
            "image_dir": "/tmp/evileye_checked_writes",
            "preview_width": 300,
            "preview_height": 150,
        }
        self.attempts = 0

    def get_params(self):
        return self.params

    def get_cameras_params(self):
        return []

    def query_once(self, query, values):
        self.attempts += 1
        raise psycopg2.OperationalError("database unavailable")

    def query(self, query, values):
        pytest.fail("queued adapters must not use the error-swallowing query API")


@pytest.mark.parametrize(
    ("adapter_type", "config", "item"),
    [
        (
            DatabaseAdapterAttributeEvents,
            {"event_name": "AttributeEvent"},
            (QueryType.INSERT, sql.SQL("INSERT"), [], None, None, None, None),
        ),
        (DatabaseAdapterCamEvents, {"event_name": "CamEvent"}, (sql.SQL("INSERT"), [])),
        (
            DatabaseAdapterFieldOfViewEvents,
            {},
            (QueryType.INSERT, sql.SQL("INSERT"), [], None),
        ),
        (
            DatabaseAdapterObjects,
            {},
            (QueryType.INSERT, sql.SQL("INSERT RETURNING record_id"), [], None, None, None),
        ),
        (DatabaseAdapterSystemEvents, {}, (sql.SQL("INSERT"), [])),
        (
            DatabaseAdapterZoneEvents,
            {"event_name": "ZoneEvent"},
            (QueryType.UPDATE, sql.SQL("UPDATE RETURNING box_entered, zone_coords"), [], None, None, None),
        ),
    ],
)
def test_queued_adapters_retry_checked_write_and_report_terminal_failure(
    adapter_type, config, item
):
    database = _Database()
    adapter = adapter_type(database)
    adapter.set_params(table_name="events", **config)
    adapter.queue_in.put_nowait(item)

    # Run the actual shared worker loop synchronously so the bounded retry and
    # terminal failure accounting can be checked without starting a thread.
    adapter._execute_query()

    assert database.attempts == 3
    stats = adapter.get_runtime_stats()
    assert stats["terminal_write_failures"] == 1
    assert stats["processed_items"] == 0
    assert stats["queue_size"] == 0
    assert stats["degraded"] is True
    assert "database unavailable" in stats["last_error"]


def test_zone_adapter_uses_the_shared_database_worker():
    assert DatabaseAdapterZoneEvents._execute_query is DatabaseAdapterBase._execute_query


class _SuccessfulDatabase(_Database):
    def __init__(self, result):
        super().__init__()
        self.result = result

    def query_once(self, query, values):
        self.attempts += 1
        return self.result


def test_post_commit_object_image_failure_is_reported_without_replaying_insert():
    from types import SimpleNamespace

    database = _SuccessfulDatabase([(1, [10, 20, 30, 40])])
    adapter = DatabaseAdapterObjects(database)
    adapter.set_params(table_name="objects")
    def fail_image_save(*args, **kwargs):
        raise OSError("disk full")

    adapter._save_image = fail_image_save
    adapter.queue_in.put_nowait(
        (
            QueryType.INSERT,
            sql.SQL("INSERT RETURNING record_id, bounding_box"),
            [],
            "preview.jpg",
            "frame.jpg",
            SimpleNamespace(image=object()),
        )
    )

    adapter._execute_query()

    stats = adapter.get_runtime_stats()
    assert database.attempts == 1
    assert stats["terminal_write_failures"] == 1
    assert stats["processed_items"] == 1
    assert "disk full" in stats["last_error"]


def test_zone_event_without_image_still_notifies_persisted_event(monkeypatch):
    from evileye.database_controller import db_adapter_zone_events as zone_module
    from evileye.database_controller.constants import EventType

    database = _SuccessfulDatabase([([10, 20, 30, 40], [[0, 0], [1, 0], [1, 1]])])
    adapter = DatabaseAdapterZoneEvents(database)
    adapter.set_params(table_name="zone_events", event_name="ZoneEvent")
    notifications = []
    monkeypatch.setattr(zone_module.threading_events, "notify", notifications.append)
    adapter.queue_in.put_nowait(
        (
            QueryType.INSERT,
            sql.SQL("INSERT RETURNING box_entered, zone_coords"),
            [],
            "preview.jpg",
            "frame.jpg",
            None,
        )
    )

    adapter._execute_query()

    assert database.attempts == 1
    assert notifications == [EventType.NEW_EVENT]
    assert adapter.get_runtime_stats()["processed_items"] == 1


def test_object_event_invalid_returning_row_is_reported_and_notified(monkeypatch):
    from evileye.database_controller import db_adapter_objects as objects_module
    from evileye.database_controller.constants import EventType

    database = _SuccessfulDatabase([(1,)])
    adapter = DatabaseAdapterObjects(database)
    adapter.set_params(table_name="objects")
    notifications = []
    monkeypatch.setattr(objects_module.threading_events, "notify", notifications.append)
    adapter.queue_in.put_nowait(
        (QueryType.INSERT, sql.SQL("INSERT RETURNING record_id, bounding_box"), [], "p", "f", None)
    )

    adapter._execute_query()

    stats = adapter.get_runtime_stats()
    assert database.attempts == 1
    assert stats["terminal_write_failures"] == 1
    assert stats["processed_items"] == 1
    assert notifications == [EventType.HANDLER_NEW_OBJECT]


def test_zone_event_invalid_returning_row_is_reported_and_notified(monkeypatch):
    from evileye.database_controller import db_adapter_zone_events as zone_module
    from evileye.database_controller.constants import EventType

    database = _SuccessfulDatabase([(None, None)])
    adapter = DatabaseAdapterZoneEvents(database)
    adapter.set_params(table_name="zone_events", event_name="ZoneEvent")
    notifications = []
    monkeypatch.setattr(zone_module.threading_events, "notify", notifications.append)
    adapter.queue_in.put_nowait(
        (
            QueryType.INSERT,
            sql.SQL("INSERT RETURNING box_entered, zone_coords"),
            [],
            "preview.jpg",
            "frame.jpg",
            None,
        )
    )

    adapter._execute_query()

    stats = adapter.get_runtime_stats()
    assert database.attempts == 1
    assert stats["terminal_write_failures"] == 1
    assert stats["processed_items"] == 1
    assert notifications == [EventType.NEW_EVENT]
