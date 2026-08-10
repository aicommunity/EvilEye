import time
from .db_adapter import DatabaseAdapterBase
from .constants import EventType, QueryType
import json
from ..utils.utils import ObjectResultEncoder
import copy
import datetime
from timeit import default_timer as timer
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql


class DatabaseAdapterCamEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)

    def set_params_impl(self):
        super().set_params_impl()
        self.event_name = self.params['event_name']

    def _insert_impl(self, obj):
        fields, data = self._prepare_for_saving(obj)
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((insert_query, data))

    def _update_impl(self, obj):
        pass

    def _process_queue_item(self, item):
        query_string, data = item

        if query_string is None:
            return

        self.db_controller.query(query_string, data)
        threading_events.notify(EventType.NEW_EVENT)

    def _prepare_for_saving(self, event) -> tuple[list, list]:
        from evileye.utils.camera_event_label import camera_event_identity

        identity = camera_event_identity(
            source_names=getattr(event, "source_names", None),
            address=getattr(event, "camera_address", ""),
        )
        fields_for_saving = {
            "camera_full_address": identity,
            "time_stamp": event.timestamp,
            "event_id": event.event_id,
            "connection_status": event.con_status,
            "project_id": self.db_controller.get_project_id(),
            "job_id": self.db_controller.get_job_id(),
        }
        return list(fields_for_saving.keys()), list(fields_for_saving.values())
