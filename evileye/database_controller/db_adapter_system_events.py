import time
from .db_adapter import DatabaseAdapterBase
from .constants import EventType
from psycopg2 import sql
from ..utils import threading_events


class DatabaseAdapterSystemEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)

    def set_params_impl(self):
        super().set_params_impl()
        self.event_name = 'SystemEvent'

    def _insert_impl(self, event):
        fields, data = self._prepare_for_saving(event)
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((insert_query, data))

    def _update_impl(self, event):
        # No updates for system events
        pass

    def _process_queue_item(self, item):
        query_string, data = item

        if query_string is None:
            return

        self.db_controller.query(query_string, data)
        threading_events.notify(EventType.NEW_EVENT)

    def _prepare_for_saving(self, event) -> tuple[list, list]:
        fields_for_saving = {
            'event_id': event.event_id,
            'time_stamp': event.timestamp,
            'event_type': event.event_type,
            'project_id': self.db_controller.get_project_id(),
            'job_id': self.db_controller.get_job_id()
        }
        return list(fields_for_saving.keys()), list(fields_for_saving.values())


