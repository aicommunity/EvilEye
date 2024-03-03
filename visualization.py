from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout, QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QPixmap
import PyQt5.QtCore as QtCore
import sys
import cv2
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QTimer, QMutex
import json
import capture
from object_detector import object_detection_yolov8
import argparse
from objects_handler.objects_handler import ObjectsHandler
from utils import utils


# Собственный класс для label, чтобы переопределить двойной клик мышкой
class MyLabel(QLabel):
    double_click_signal = pyqtSignal()

    def __init__(self):
        super(MyLabel, self).__init__()
        self.is_full = False

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_click_signal.emit()


class VideoThread(QThread):
    thread_counter = 0
    rows = 0
    cols = 0
    # Сигнал, который отвечает за обновление label, в котором отображается изображение из потока
    update_image_signal = pyqtSignal(list)

    def __init__(self, params, camera, labels, rows, cols, obj_handler):
        super().__init__()
        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols

        self.labels = labels
        self.run_flag = True
        self.split = params['split']
        self.fps = 30
        self.source_params = params
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.capture = camera
        self.detectors = []
        self.det_params = None
        self.bboxes_coords = []
        self.confidences = []
        self.class_ids = []
        self.handler = obj_handler

        # Если выбран модуль детекции, настраиваем детектор
        if params['module']['name'] == 'detection':
            self.det_params = params['module']['det_params']
            if self.split:
                for i in range(self.source_params['num_split']):
                    self.detectors.append(object_detection_yolov8.ObjectDetectorYoloV8())
                    self.detectors[i].set_params(**self.det_params)
                    self.detectors[i].init()
            else:
                self.detectors.append(object_detection_yolov8.ObjectDetectorYoloV8())
                self.detectors[-1].set_params(**self.det_params)
                self.detectors[-1].init()

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.process_image)

        # Определяем количество потоков в зависимости от параметра split
        if self.source_params['split']:  # Если включен сплит, то увеличиваем количество потоков на соотв. число
            VideoThread.thread_counter += self.source_params['num_split']
        else:
            VideoThread.thread_counter += 1

    def run(self):
        if self.source_params['source'] == 'file':  # Проигрывание роликов с указанным fps, если запускаем из файла
            self.fps = self.source_params['fps']
            self.timer.start(int(1000 // self.fps))
            loop = QtCore.QEventLoop()
            loop.exec_()
        else:
            while self.run_flag:
                self.process_image()
        self.capture.release()

    def process_image(self):
        ret, frames = self.capture.process(split_stream=self.source_params['split'],
                                           num_split=self.source_params['num_split'],
                                           src_coords=self.source_params['src_coords'])
        if ret:
            for count, frame in enumerate(frames):
                if self.source_params['module']['name'] == 'detection':
                    frame_objects = self.detectors[count].process(frame, all_roi=self.det_params['roi'][count])
                    self.handler.append(frame_objects)
                    det_id = self.detectors[count].id
                    utils.draw_boxes_tracking(frame, self.handler.get('new'), det_id, self.detectors[count].model.names)
                conv_img = self.convert_cv_qt(frame)
                # Сигнал из потока для обновления label на новое изображение
                self.update_image_signal.emit([conv_img, self.thread_num + count])
        else:
            self.capture.reset()

    def stop(self):
        self.run_flag = False
        self.wait()

    def convert_cv_qt(self, cv_img):
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(int(a.geometry().width() / VideoThread.cols),
                                            int(a.geometry().height() / VideoThread.rows), Qt.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)


class App(QWidget):
    def __init__(self, params, win_width, win_height):
        super().__init__()
        self.setWindowTitle("EvilEye")
        self.resize(win_width, win_height)
        self.adjustSize()

        self.params = params
        self.rows = self.params['num_height']
        self.cols = self.params['num_width']
        self.sources = self.params['sources']
        self.num_sources = len(self.params['sources'])
        self.num_labels = 0
        self.labels = []
        self.threads = []
        self.hlayouts = []
        self.cameras = []

        for i in range(self.num_sources):
            if self.params['sources'][i]['split']:
                self.num_labels += self.params['sources'][i]['num_split']
                self.sources.append(self.params['sources'][i].copy())
            else:
                self.num_labels += 1
        self.handler = ObjectsHandler(self.num_labels)
        vertical_layout = QVBoxLayout()
        for i in range(self.rows):
            self.hlayouts.append(QHBoxLayout())
            vertical_layout.addLayout(self.hlayouts[-1])
        self.setLayout(vertical_layout)
        self.setup_layout()
        self.init_captures()  # Инициализируем объекты захват из источников
        self.setup_threads()  # Создаем и запускаем потоки

    def init_captures(self):
        for i in range(self.num_sources):
            src_params = self.sources[i]
            capture_params = {'source': src_params['source'], 'filename': src_params['camera'],
                              'apiPreference': src_params['apiPreference'], 'split': src_params['split'],
                              'num_split': src_params['num_split'], 'src_coords': src_params['src_coords']}
            camera = capture.VideoCapture()
            camera.set_params(**capture_params)
            camera.init()
            self.cameras.append(camera)

    def setup_threads(self):
        for i in range(self.num_sources):
            self.threads.append(VideoThread(self.sources[i], self.cameras[i], self.labels, self.rows, self.cols, self.handler))
            self.threads[-1].update_image_signal.connect(self.update_image)  # Сигнал из потока для обновления label на новое изображение
            self.threads[-1].start()

    def setup_layout(self):
        self.layout().setContentsMargins(0, 0, 0, 0)
        grid_cols = 0
        grid_rows = 0
        for i in range(self.num_labels):
            self.labels.append(MyLabel())
            # Изменяем размер изображения по двойному клику
            self.labels[-1].double_click_signal.connect(self.change_screen_size)
            self.labels[-1].setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

            # Добавляем виджеты в layout в зависимости от начальных параметров (кол-во изображений по ширине и высоте)
            if grid_cols > self.cols - 1:
                grid_cols = 0
                grid_rows += 1
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignCenter)
                grid_cols += 1
            else:
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignCenter)
                grid_cols += 1

    def closeEvent(self, event):
        for thread in self.threads:
            thread.stop()
        event.accept()

    @pyqtSlot(list)
    def update_image(self, thread_data):
        # Обновляет label, в котором находится изображение
        self.labels[thread_data[1]].setPixmap(thread_data[0])

    @pyqtSlot()
    def change_screen_size(self):
        sender = self.sender()
        if sender.is_full:
            sender.is_full = False
            VideoThread.rows = self.rows
            VideoThread.cols = self.cols
            for label in self.labels:
                if sender != label:
                    label.show()
        else:
            sender.is_full = True
            for label in self.labels:
                if sender != label:
                    label.hide()
            VideoThread.rows = 1
            VideoThread.cols = 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('fullpath', help='Full path to json file with cameras and modules params',
                        type=str, default=None, nargs="?")
    args = parser.parse_args()
    if args.fullpath is None:
        params_file = open('samples/visual_sample.json')
    else:
        params_file = open(args.fullpath)
    data = json.load(params_file)
    app = QApplication(sys.argv)
    a = App(data, 1280, 720)
    a.show()
    sys.exit(app.exec_())
