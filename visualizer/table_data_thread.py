from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop, QTimer
from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
from timeit import default_timer as timer
from utils import utils
from queue import Queue
import time
import cv2


class TableDataThread(QThread):
    append_record_signal = pyqtSignal(list)
    update_record_signal = pyqtSignal(list)

    def __init__(self, fps, db_controller):
        super().__init__()

        self.queue = Queue()
        self.db_controller = db_controller
        self.fps = fps

        self.run_flag = False

    def append_data(self, data):
        self.queue.put(data)

    def start_thread(self):
        self.run_flag = True
        self.start()

    def stop_thread(self):
        self.run_flag = False
        print('Data preparation thread stopped')

    def run(self):
        while self.run_flag:
            elapsed_seconds = self.process_query()
            sleep_seconds = 1. / self.fps - elapsed_seconds
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)
            else:
                time.sleep(0.01)

    def process_query(self):
        try:
            query_type, query_string, data = self.queue.get()
        except ValueError:
            return 0
        begin_it = timer()
        # print(data)
        records = self.db_controller.query(query_string, data)
        end_it = timer()
        elapsed_seconds = end_it - begin_it
        # print(records)
        if query_type == 'Insert':
            self.append_record_signal.emit(records)
        elif query_type == 'Update':
            self.update_record_signal.emit(records)
        return elapsed_seconds

