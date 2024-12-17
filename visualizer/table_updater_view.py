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
from PyQt6.QtCore import QObject, QThread, pyqtSignal, QEventLoop, QTimer
from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap


class TableUpdater(QObject):
    append_record_signal = pyqtSignal()
    update_record_signal = pyqtSignal()

    def __init__(self, table_name, qt_slot_insert, qt_slot_update):
        super().__init__()
        self.qt_slot_insert = qt_slot_insert
        self.qt_slot_update = qt_slot_update
        self.data_thread = None
        self.fps = 5
        self.table_name = table_name
        self.append_record_signal.connect(self.qt_slot_insert)
        self.update_record_signal.connect(self.qt_slot_update)
        event.subscribe('handler new object', self.update)
        event.subscribe('handler update object', self.update_on_lost)

    def update(self, last_db_row):
        self.append_record_signal.emit()

    def update_on_lost(self, db_row_num):
        self.update_record_signal.emit()
