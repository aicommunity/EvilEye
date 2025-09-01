try:
    from PyQt6.QtCore import QThread, QMutex, pyqtSignal, QEventLoop, QTimer, pyqtSlot
    from PyQt6 import QtGui
    from PyQt6.QtCore import Qt, QPointF, QRectF
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QPolygonF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QThread, QMutex, pyqtSignal, QEventLoop, QTimer, pyqtSlot
    from PyQt5 import QtGui
    from PyQt5.QtCore import Qt, QPointF, QRectF
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QBrush, QColor, QPolygonF
    pyqt_version = 5

from timeit import default_timer as timer
from ..utils import utils
from queue import Queue
from queue import Empty
import copy
import time
import cv2
from ..events_detectors.zone import ZoneForm


class VideoThread(QThread):
    handler = None
    thread_counter = 0
    rows = 0
    cols = 0
    # Сигнал, отвечающий за обновление label, в котором отображается изображение из потока
    update_image_signal = pyqtSignal(int, QPixmap)
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int, QPixmap)

    def __init__(self, source_id, fps, rows, cols, show_debug_info, font_params, text_config=None):
        super().__init__()

        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols
        self.queue = Queue(maxsize=fps)

        self.thread_num = VideoThread.thread_counter
        self.source_id = source_id
        self.zones = None
        self.show_zones = False
        self.is_add_zone_clicked = False

        self.run_flag = False
        self.show_debug_info = show_debug_info
        self.fps = fps
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.det_params = None
        self.text_config = text_config or {}  # Text configuration for rendering

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.process_image)
        self.display_zones_signal.connect(self.display_zones)

        self.widget_width = 1920
        self.widget_height = 1080

        if font_params:
            self.font_scale = font_params.get('scale', 3)
            self.font_thickness = font_params.get('thickness', 5)
            self.font_color = font_params.get('color', (0, 0, 255))
        else:
            self.font_scale = 3
            self.font_thickness = 5
            self.font_color = (0, 0, 255)

        # Определяем количество потоков в зависимости от параметра split
        VideoThread.thread_counter += 1

    def start_thread(self):
        self.run_flag = True
        self.start()

    def append_data(self, data):
        if self.queue.full():
            self.queue.get()
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
        self.widget_width = width
        self.widget_height = height

    def convert_cv_qt(self, cv_img, widget_width, widget_height) -> QPixmap:
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        if self.is_add_zone_clicked:
            zones_window_image = convert_to_qt.scaled(int(widget_width), int(widget_height),
                                                      Qt.AspectRatioMode.KeepAspectRatio)
            self.is_add_zone_clicked = False
            self.add_zone_signal.emit(self.thread_num, QPixmap.fromImage(zones_window_image))
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(int(widget_width / VideoThread.cols),
                                            int(widget_height / VideoThread.rows), Qt.AspectRatioMode.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)

    def draw_zones(self, image: QPixmap, zones: dict):
        # print(zones)
        if not zones:
            return

        if self.source_id not in zones or not zones[self.source_id]:
            return

        src_zones = zones[self.source_id]
        brush = QBrush(QColor(255, 0, 0, 128))
        pen = QPen(Qt.GlobalColor.red)
        painter = QPainter(image)
        painter.setPen(pen)
        painter.setBrush(brush)
        width, height = image.width(), image.height()
        for zone_type, zone_coords, _ in src_zones:
            coords = [QPointF(point[0] * width, point[1] * height) for point in zone_coords]
            if ZoneForm(zone_type) == ZoneForm.Rectangle:
                rect = QRectF(coords[0], coords[2])
                painter.drawRect(rect)
            elif ZoneForm(zone_type) == ZoneForm.Polygon:
                painter.drawPolygon(QPolygonF(coords))

    def process_image(self):
        try:
            frame, track_info, source_name, source_duration_secs, debug_info = self.queue.get()
            begin_it = timer()
            utils.draw_boxes_tracking(frame, track_info, source_name, source_duration_secs,
                                      self.font_scale, self.font_thickness, self.font_color,
                                      text_config=self.text_config)
            if self.show_debug_info:
                utils.draw_debug_info(frame, debug_info)
            qt_image = self.convert_cv_qt(frame.image, self.widget_width, self.widget_height)
            if self.show_zones:
                self.draw_zones(qt_image, self.zones)
            end_it = timer()
            elapsed_seconds = end_it - begin_it
            # Сигнал из потока для обновления label на новое изображение
            self.update_image_signal.emit(self.thread_num, qt_image)
            return elapsed_seconds
        except Empty:
            return 0
        except ValueError:
            return 0

    def stop_thread(self):
        self.run_flag = False
        print('Visualization stopped')

    @pyqtSlot(dict)
    def display_zones(self, zones):
        if zones:
            self.show_zones = True
            self.zones = zones
        else:
            self.show_zones = False

    @pyqtSlot(int)
    def add_zone_clicked(self, thread_id):
        if self.thread_num == thread_id:
            self.is_add_zone_clicked = True
