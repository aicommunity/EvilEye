from abc import ABC, abstractmethod
import datetime
from visualization_modules.video_thread import VideoThread
import core
from psycopg2 import sql
import copy
from capture.video_capture_base import CaptureImage
from objects_handler.objects_handler import ObjectResultList
from timeit import default_timer as timer
from visualization_modules.table_data_thread import TableDataThread
from utils import threading_events


class TableUpdater(core.EvilEyeBase):
    def __init__(self, table_name, qt_slot_insert, qt_slot_update, db_controller):
        super().__init__()
        self.qt_slot_insert = qt_slot_insert
        self.qt_slot_update = qt_slot_update
        self.data_thread = None
        self.fps = 5
        self.db_controller = db_controller
        self.table_name = table_name

    def default(self):
        pass

    def update(self, last_db_row):
        query_type = 'Insert'
        fields = self.params.keys()
        start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        query = sql.SQL('SELECT {fields} FROM {table} WHERE record_id = %s AND time_stamp > %s;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        # print(f'COUNT: {last_db_row}')
        self.data_thread.append_data((query_type, query, (last_db_row, start_time)))

    def update_on_lost(self, db_row_num):
        query_type = 'Update'
        fields = self.params.keys()
        query = sql.SQL('SELECT {fields} FROM {table} WHERE record_id = %s;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        # print(f'COUNT: {last_db_row}')
        self.data_thread.append_data((query_type, query, (db_row_num, )))

    def init_impl(self):
        self.data_thread = TableDataThread(self.fps, self.db_controller)
        self.data_thread.append_record_signal.connect(self.qt_slot_insert)
        self.data_thread.update_record_signal.connect(self.qt_slot_update)
        threading_events.subscribe('handler new object', self.update)
        threading_events.subscribe('handler update object', self.update_on_lost)

    def set_params_impl(self):
        pass

    def release_impl(self):
        self.data_thread.stop_thread()
        self.data_thread = None

    def reset_impl(self):
        pass

    def start(self):
        self.data_thread.start_thread()

    def stop(self):
        if self.data_thread:
            self.data_thread.stop_thread()
            self.data_thread = None
