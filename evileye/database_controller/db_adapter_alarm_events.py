"""PostgreSQL adapter for generic plugin alarm events."""

from __future__ import annotations

from queue import Full

from psycopg2 import sql
from psycopg2.extras import Json

from .db_adapter import DatabaseAdapterBase
from ..utils import threading_events
from .constants import EventType


class DatabaseAdapterAlarmEvents(DatabaseAdapterBase):
    def set_params_impl(self):
        super().set_params_impl()
        self.event_name = "AlarmEvent"

    def _insert_impl(self, event):
        if not self.run_flag or not self.query_thread.is_alive():
            error = RuntimeError("Alarm database adapter worker is not running")
            self._record_failure('enqueue alarm', error, category='enqueue')
            raise error
        fields = [
            "event_id", "alarm_id", "time_stamp", "alarm_type", "severity",
            "source_id", "source_name", "details", "project_id", "job_id",
        ]
        values = [
            event.event_id,
            event.alarm_id,
            event.timestamp,
            event.alarm_type,
            event.severity,
            event.source_id,
            event.source_name,
            Json(event.details),
            self.db_controller.get_project_id(),
            self.db_controller.get_job_id(),
        ]
        query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) ON CONFLICT (alarm_id) DO NOTHING").format(
            sql.Identifier(self.table_name),
            sql.SQL(", ").join(map(sql.Identifier, fields)),
            sql.SQL(", ").join(sql.Placeholder() * len(fields)),
        )
        try:
            self.queue_in.put_nowait((query, values))
        except Full as exc:
            error = RuntimeError(
                f"Alarm database queue is full (maxsize={self.queue_maxsize})"
            )
            self._record_failure('enqueue alarm', error, category='enqueue')
            raise error from exc

    def _update_impl(self, event):
        return None

    def _process_queue_item(self, item):
        query, values = item
        self.db_controller.query_checked(query, values)
        threading_events.notify(EventType.NEW_EVENT)

