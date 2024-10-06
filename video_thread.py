from PyQt5.QtCore import QThread, pyqtSignal, QEventLoop, QTimer
from PyQt5 import QtGui
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from timeit import default_timer as timer
from utils import utils
from queue import Queue
import time
import cv2


class VideoThread(QThread):
    handler = None
    thread_counter = 0
    rows = 0
    cols = 0
    # Сигнал, отвечающий за обновление label, в котором отображается изображение из потока
    update_image_signal = pyqtSignal(list)

    def __init__(self, params, rows, cols):
        super().__init__()
        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols
        self.queue = Queue()

        self.thread_num = VideoThread.thread_counter

        self.run_flag = False
        self.split = params['split']
        self.fps = 30
        self.source_params = params
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.det_params = None

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.process_image)

        # Определяем количество потоков в зависимости от параметра split
        VideoThread.thread_counter += 1

    def start_thread(self):
        self.run_flag = True
        self.start()

    def append_data(self, data):
        self.queue.put(data)

    def run(self):
        if self.source_params['source'] == 'file':  # Проигрывание роликов с указанным fps, если запускаем из файла
            self.fps = self.source_params['fps']
            self.timer.start(int(1000 // self.fps))
            loop = QEventLoop()
            loop.exec_()
        else:
            while self.run_flag:
                begin_it = timer()
                self.process_image()
                end_it = timer()
                elapsed_seconds = end_it - begin_it
                sleep_seconds = 1. / self.fps - elapsed_seconds
                if sleep_seconds > 0.0:
                    time.sleep(sleep_seconds)
                else:
                    time.sleep(0.01)

    def process_image(self):
        try:
            frame, track_info = self.queue.get()
        except ValueError:
            return
        utils.draw_boxes_tracking(frame, track_info)
        # Сигнал из потока для обновления label на новое изображение
        self.update_image_signal.emit([frame, self.thread_num])

    def stop(self):
        self.run_flag = False
        self.queue.put('STOP')
        self.wait()
        print('Video stopped')
