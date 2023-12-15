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
        self.params_file = params_file
        self.thread_num = VideoThread.thread_counter
        VideoThread.thread_counter += 1

    def run(self):
        params_file = open(self.params_file)
        data = json.load(params_file)
        cap_params = data['cap_params']
        capture_params = {'source': cap_params['source'], 'filename': cap_params['fullpath'],
                          'apiPreference': cap_params['apiPreference']}
        # capture from web cam
        video = capture.VideoCapture()
        video.init()
        video.set_params(**capture_params)
        while self._run_flag:
            ret, cv_img = video.process()
            if ret:
                image = self.convert_cv_qt(cv_img)
                self.change_pixmap_signal.emit([image, self.thread_num])
        # shut down capture system
        video.release()

    def stop(self):
        self._run_flag = False
        self.wait()

    def convert_cv_qt(self, cv_img):
        # Convert from an opencv image to QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_Qt_format = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        p = convert_to_Qt_format.scaled(640, 480, Qt.KeepAspectRatio)
        return QPixmap.fromImage(p)


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
        # create the video capture thread
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
        # connect its signal to the update_image slot
        self.threads[-1].change_pixmap_signal.connect(self.update_image)
        # start the thread
        self.threads[-1].start()

    def closeEvent(self, event):
        self.thread.stop()
        event.accept()

    @pyqtSlot(list)
    def update_image(self, data):
        """Updates the image_label with a new opencv image"""
        start = time.time()
        self.labels[data[1]].setPixmap(data[0])
        print(time.time() - start)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    a = App()
    a.resize(1280, 720)
    a.show()
    sys.exit(app.exec_())