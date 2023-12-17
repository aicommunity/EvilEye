from PyQt5 import QtGui
from PyQt5.QtWidgets import QWidget, QApplication, QLabel, QVBoxLayout, QPushButton, QFileDialog, QGridLayout, QDesktopWidget
from PyQt5.QtGui import QPixmap
import PyQt5.QtCore as QtCore
import sys
import cv2
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread, QTimer
import numpy as np
import json
import capture
import capture as cap
import time


class VideoThread(QThread):
    thread_counter = 0
    change_pixmap_signal = pyqtSignal(list)

    def __init__(self, params_file):
        super().__init__()
        self._run_flag = True
        self.fps = 30
        self.params_file = params_file
        self.thread_num = VideoThread.thread_counter
        self.timer = QTimer()
        self.timer.moveToThread(self)
        self.timer.timeout.connect(self.update_image)
        self.capture = capture.VideoCapture()
        VideoThread.thread_counter += 1

    def run(self):
        params_file = open(self.params_file)
        data = json.load(params_file)
        cap_params = data['cap_params']
        capture_params = {'source': cap_params['source'], 'filename': cap_params['fullpath'],
                          'apiPreference': cap_params['apiPreference']}
        self.capture.init()
        self.capture.set_params(**capture_params)
        if cap_params['source'] == 'file':
            self.fps = cap_params['fps']
            # Проигрывание роликов с указанным fps
            self.timer.start(int(1000//self.fps))
            loop = QtCore.QEventLoop()
            loop.exec_()
        else:
            while self._run_flag:
                self.update_image()
        self.capture.release()

    def update_image(self):
        ret, cv_img = self.capture.process()
        if ret:
            image = self.convert_cv_qt(cv_img)
            self.change_pixmap_signal.emit([image, self.thread_num])

    def stop(self):
        self._run_flag = False
        self.wait()

    def convert_cv_qt(self, cv_img):
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        scaled_image = convert_to_qt.scaled(640, 480, Qt.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)


class App(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Qt live label demo")
        self.display_width = 640
        self.display_height = 480
        self.labels = []
        self.threads = []
        self.rows = 0
        self.cols = 0
        self.button = QPushButton("Add source", self)
        layout = QGridLayout()
        layout.addWidget(self.button, 4, 0, -1, 0, alignment=QtCore.Qt.AlignBottom)
        self.setLayout(layout)
        self.button.clicked.connect(self.start_thread)

    def start_thread(self):
        fname = QFileDialog.getOpenFileName(self, "Open File", "", "All Files (*)")
        # Создаем поток, в котором будет захватываться видео
        self.threads.append(VideoThread(str(fname[0])))
        self.labels.append(QLabel(self))
        self.labels[-1].resize(self.display_width, self.display_height)
        if self.cols > 2:
            self.cols = 0
            self.rows += 1
            self.layout().addWidget(self.labels[-1], self.rows, self.cols)
            self.cols += 1
        else:
            self.layout().addWidget(self.labels[-1], self.rows, self.cols)
            self.cols += 1
        # Подключаем сигнал из потока к функции обновления изображения
        self.threads[-1].change_pixmap_signal.connect(self.update_image)
        # Запускаем поток
        self.threads[-1].start()

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()

    @pyqtSlot(list)
    def update_image(self, data):
        # Обновляет label, в котором находится изображение
        self.labels[data[1]].setPixmap(data[0])


if __name__ == "__main__":
    app = QApplication(sys.argv)
    a = App()
    a.resize(1280, 720)
    a.show()
    sys.exit(app.exec_())