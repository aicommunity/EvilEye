from PyQt6.QtCore import QThread, pyqtSignal, QEventLoop, QTimer
from PyQt6 import QtGui
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QPixmap
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

    def __init__(self, source_id, fps, rows, cols):
        super().__init__()
        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols
        self.queue = Queue()

        self.thread_num = VideoThread.thread_counter
        self.source_id = source_id

        self.run_flag = False
        #self.split = params['split']
        self.fps = fps
        #self.source_params = params
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.det_params = None

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.process_image)

        self.widget_width = 1920
        self.widget_height = 1080

        # Определяем количество потоков в зависимости от параметра split
        VideoThread.thread_counter += 1

    def start_thread(self):
        self.run_flag = True
        self.start()

    def append_data(self, data):
        self.queue.put(data)

    def run(self):
        while self.run_flag:
            elapsed_seconds = self.process_image()
            sleep_seconds = 1. / self.fps - elapsed_seconds
            if sleep_seconds > 0.0:
                time.sleep(sleep_seconds)
            else:
                time.sleep(0.01)

    def set_main_widget_size(self, width, height):
        self.widget_witdth = width
        self.widget_height = height

    def convert_cv_qt(self, cv_img, widget_witdth, widget_height):
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(int(widget_witdth / VideoThread.cols),
                                            int(widget_height / VideoThread.rows), Qt.AspectRatioMode.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)

    def process_image(self):
        try:
            frame, track_info, source_name, source_duration_secs = self.queue.get()
        except ValueError:
            return 0
        begin_it = timer()
        utils.draw_boxes_tracking(frame, track_info, source_name, source_duration_secs)
        qt_image = self.convert_cv_qt(frame.image, self.widget_width, self.widget_height)
        end_it = timer()
        elapsed_seconds = end_it - begin_it
        # Сигнал из потока для обновления label на новое изображение
        self.update_image_signal.emit([qt_image, self.thread_num])
        return elapsed_seconds

    def stop_thread(self):
        self.run_flag = False
        print('Visualization stopped')
