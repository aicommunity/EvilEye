from abc import ABC, abstractmethod
import datetime
from visualizer.video_thread import VideoThread
import core
from psycopg2 import sql
import copy
from capture.video_capture_base import CaptureImage
from objects_handler.objects_handler import ObjectResultList
from timeit import default_timer as timer
from visualizer.table_data_thread import TableDataThread
from utils import event


class TableUpdater(core.EvilEyeBase):
    def __init__(self, table_name, pyqt_slot, db_controller):
        super().__init__()
        self.qt_slot = pyqt_slot
        self.data_thread = None
        self.fps = 5
        self.db_controller = db_controller
        self.table_name = table_name

    def default(self):
        pass

    def update(self, last_db_row):
        fields = self.params.keys()
        start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        query = sql.SQL('SELECT count, {fields} FROM {table} WHERE count = %s AND time_stamp > %s;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        # print(f'COUNT: {last_db_row}')
        self.data_thread.append_data((query, (last_db_row, start_time)))

    def init_impl(self):
        self.data_thread = TableDataThread(self.fps, self.db_controller)
        self.data_thread.update_table_signal.connect(self.qt_slot)
        event.subscribe('handler new object', self.update)

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
        self.data_thread.stop_thread()
        self.data_thread = None
