from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QPushButton, QFileDialog, QGridLayout, QVBoxLayout, \
    QHBoxLayout, QSizePolicy
from PyQt5.QtGui import QPixmap
import PyQt5.QtCore as QtCore
import sys
import cv2
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QTimer
import json
import capture
from object_detector import object_detection_yolov8
import argparse


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

    def __init__(self, params, labels, rows, cols):
        super().__init__()
        VideoThread.rows = rows  # Количество строк и столбцов для правильного перевода изображения в полный экран
        VideoThread.cols = cols

        self.labels = labels
        self.run_flag = True
        self.split = params['split']
        self.fps = 30
        self.source_params = params
        self.thread_num = VideoThread.thread_counter  # Номер потока для определения, какой label обновлять
        self.capture = capture.VideoCapture()
        self.detector = None
        self.det_params = None
        self.bboxes_coords = []
        self.confidences = []
        self.class_ids = []

        # Если выбран модуль детекции, настраиваем детектор
        if params['module']['name'] == 'detection':
            self.det_params = params['module']['det_params']
            self.detector = object_detection_yolov8.ObjectDetectorYoloV8(self.det_params['model'])
            self.detector.init()
            self.detector.set_params(**self.det_params)

        # Таймер для задания fps у видеороликов
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.update_image)

        # Определяем количество потоков в зависимости от параметра split
        if self.source_params['split']:  # Если включен сплит, то увеличиваем количество потоков на соотв. число
            VideoThread.thread_counter += self.source_params['num_split']
        else:
            VideoThread.thread_counter += 1

    def run(self):
        capture_params = {'source': self.source_params['source'], 'filename': self.source_params['camera'],
                          'apiPreference': self.source_params['apiPreference']}
        self.capture.init()
        self.capture.set_params(**capture_params)
        if self.source_params['source'] == 'file':
            self.fps = self.source_params['fps']
            # Проигрывание роликов с указанным fps, если запускаем из файла
            self.timer.start(int(1000 // self.fps))
            loop = QtCore.QEventLoop()
            loop.exec_()
        else:
            while self.run_flag:
                self.update_image()
        self.capture.release()

    def update_image(self):
        ret, images = self.capture.process(split_stream=self.source_params['split'],
                                           num_split=self.source_params['num_split'],
                                           roi=self.source_params['roi'])
        if ret:
            for count, image in enumerate(images):
                if self.source_params['module']['name'] == 'detection':
                    bboxes_coord, confidence, class_id = self.detector.process(image, all_roi=None)
                    self.bboxes_coords.append(bboxes_coord)
                    self.confidences.append(confidence)
                    self.class_ids.append(class_id)
                conv_img = self.convert_cv_qt(image)
                # Сигнал из потока для обновления label на новое изображение
                self.update_image_signal.emit([conv_img, self.thread_num + count])

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

        for i in range(self.num_sources):
            if self.params['sources'][i]['split']:
                self.num_labels += self.params['sources'][i]['num_split']
            else:
                self.num_labels += 1
        vertical_layout = QVBoxLayout()
        for i in range(self.rows):
            self.hlayouts.append(QHBoxLayout())
            vertical_layout.addLayout(self.hlayouts[-1])
        self.setLayout(vertical_layout)
        self.setup_layout()
        self.setup_threads()

    def setup_threads(self):
        for i in range(self.num_sources):
            self.threads.append(VideoThread(self.sources[i], self.labels, self.rows, self.cols))
            self.threads[-1].update_image_signal.connect(self.update_image)
            self.threads[-1].start()

    def setup_layout(self):
        self.layout().setContentsMargins(0, 0, 0, 0)
        grid_cols = 0
        grid_rows = 0
        for i in range(self.num_labels):
            self.labels.append(MyLabel())
            self.labels[-1].double_click_signal.connect(self.changeScreenSize)
            self.labels[-1].setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)
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
    def changeScreenSize(self):
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
