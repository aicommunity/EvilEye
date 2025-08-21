import time
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QSizePolicy,
        QComboBox, QFormLayout, QSpacerItem, QListView, QCheckBox, QPushButton
    )
    from PyQt6.QtGui import QIcon
    from PyQt6 import QtCore
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QThread
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QSizePolicy,
        QComboBox, QFormLayout, QSpacerItem, QListView, QCheckBox, QPushButton
    )
    from PyQt5.QtGui import QIcon
    from PyQt5 import QtCore
    from PyQt5.QtGui import QPixmap
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QThread
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from ....utils import utils
from timeit import default_timer as timer
import cv2
import os
from ..db_connection_window import DatabaseConnectionWindow
from ....capture.video_capture_base import CaptureDeviceType
from .. import parameters_processing
from ....capture.video_capture import VideoCapture
from urllib.parse import urlparse
from .. import parameters_processing


class SourceWidget(QWidget):
    update_image_signal = pyqtSignal()
    conn_win_signal = pyqtSignal()

    def __init__(self, params, creds, parent=None):
        super().__init__(parent)

        self.params = params
        self.credentials = creds
        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.split_check_boxes = []
        self.coords_edits = []
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.stop_capture = True
        self.capture_labels = []
        self.sources_history = None

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.horizontal_layout = QHBoxLayout()
        self.thread = None
        self.src_history_added = False

        self.horizontal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._setup_layout(self.params)
        self.setLayout(self.horizontal_layout)

    def show_src_history(self, src_list: QWidget):
        if not self.src_history_added:
            self.src_history_added = True
            spacer = QSpacerItem(400, 10)
            self.v_layout.insertItem(1, spacer)
        self.history_btn.setEnabled(False)
        self.v_layout.insertWidget(2, src_list)

    def _setup_layout(self, params):
        self.horizontal_layout.setContentsMargins(10, 10, 10, 10)
        self.v_layout = QVBoxLayout()
        self.v_layout.setAlignment(Qt.AlignmentFlag.AlignLeft)

        self.capture_v_layout = QVBoxLayout()
        self.horizontal_layout.addLayout(self.v_layout)
        capture_label = QLabel()
        self.capture_labels.append(capture_label)
        self.capture_v_layout.addWidget(capture_label)
        self.horizontal_layout.addLayout(self.capture_v_layout)

        self.source_layout = self._setup_src_form(params)
        self.v_layout.addLayout(self.source_layout)

        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.test_source_btn = QPushButton('Test source')
        self.test_source_btn.clicked.connect(self._capture_src)
        self.test_source_btn.setMaximumWidth(200)
        button_layout.addWidget(self.test_source_btn)
        self.v_layout.addLayout(button_layout)

        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.stop_source_btn = QPushButton('Stop')
        self.stop_source_btn.setEnabled(False)
        self.stop_source_btn.setMaximumWidth(200)
        self.stop_source_btn.clicked.connect(self._stop_capture)
        button_layout.addWidget(self.stop_source_btn)
        self.v_layout.addLayout(button_layout)

    @pyqtSlot()
    def _capture_src(self):
        src_params = self.get_dict()
        split, num_split = src_params['split'], src_params['num_split']

        if split:
            self._add_new_capture_label(num_split)

        for capture_label in self.capture_labels:
            if not capture_label.isVisible():
                capture_label.show()
        self.stop_source_btn.setEnabled(True)
        self.test_source_btn.setEnabled(False)

        self.thread = SrcThread(src_params, self.credentials,
                                self.width() - int(2.5 * self.source_layout.itemAt(0).geometry().width()),
                                self.height() // (num_split if num_split else 1))

        self.thread.update_image_signal.connect(self._update_label)
        is_started = self.thread.start_thread()
        if not is_started:
            print('Connection Error. Try again')
            self.stop_source_btn.setEnabled(False)
            self.test_source_btn.setEnabled(True)

    def _add_new_capture_label(self, num_split):
        for i in range(num_split - len(self.capture_labels)):
            label = QLabel()
            self.capture_v_layout.addWidget(label)
            label.hide()
            self.capture_labels.append(label)

    @pyqtSlot()
    def _stop_capture(self):
        self.thread.stop_thread()
        self.thread = None
        for capture_label in self.capture_labels:
            capture_label.hide()
        self.test_source_btn.setEnabled(True)

    @pyqtSlot(int, QPixmap)
    def _update_label(self, idx, image):
        self.capture_labels[idx].setPixmap(image)

    def _setup_src_form(self, params) -> QFormLayout:
        source_layout = QFormLayout()
        source_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        name = QLabel('Source Parameters')
        source_layout.addWidget(name)

        src_type = QComboBox()
        src_type.addItems([capture_type.name for capture_type in CaptureDeviceType])
        index = src_type.findText(params['source'])
        if index != -1:
            src_type.setCurrentIndex(index)
        source_layout.addRow('Source type', src_type)
        self.line_edit_param['source'] = src_type

        self.src_link = QLineEdit()
        self.src_link.setText(params['camera'])
        source_layout.addRow('RTSP-link or file path', self.src_link)
        self.line_edit_param['camera'] = self.src_link

        api = QComboBox()
        api.addItems([api.name for api in VideoCapture.VideoCaptureAPIs])
        index = api.findText(params['apiPreference'])
        if index != -1:
            api.setCurrentIndex(index)
        source_layout.addRow('OpenCV API', api)
        self.line_edit_param['apiPreference'] = api

        split_box = QCheckBox()
        source_layout.addRow('Split', split_box)
        split_box.setText('Split source')
        split = params.get('split', None)
        if split is None or split == '':
            split = False
        split_box.setChecked(split)
        split_box.checkStateChanged.connect(self._set_coords_line_active)
        self.split_check_boxes.append(split_box)
        self.line_edit_param['split'] = split_box

        num_split = QLineEdit()
        num_split.setText(str(params['num_split']))
        if params['split']:
            num_split.setEnabled(True)
        else:
            num_split.setEnabled(False)
        source_layout.addRow('Split number', num_split)
        self.line_edit_param['num_split'] = num_split

        split_coords = QLineEdit()
        split_coords.setText(str(params['src_coords']))
        if params['split']:
            split_coords.setEnabled(True)
            split_coords.setEnabled(True)
        else:
            split_coords.setEnabled(False)
        source_layout.addRow('Frame split', split_coords)
        self.coords_edits.append((split_coords, num_split))
        self.line_edit_param['src_coords'] = split_coords

        src_ids = QLineEdit()
        src_ids.setText(str(params['source_ids']))
        source_layout.addRow('Sources ids', src_ids)
        self.line_edit_param['source_ids'] = src_ids

        src_names = QLineEdit()
        src_names.setText(str(params['source_names']))
        source_layout.addRow('Sources names', src_names)
        self.line_edit_param['source_names'] = src_names

        loop_play = QCheckBox()
        flag = params.get('split', None)
        if flag == '' or flag is None:
            flag = False
        loop_play.setChecked(flag)
        source_layout.addRow('Loop play', loop_play)
        self.line_edit_param['loop_play'] = loop_play

        widgets = (source_layout.itemAt(i).widget() for i in range(source_layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)

        self.history_btn = QPushButton(icon=QIcon(os.path.join(utils.get_project_root(), 'icons', 'cam_history.svg')))
        self.history_btn.setIconSize(QtCore.QSize(30, 30))
        self.history_btn.setFixedSize(30, 30)
        self.history_btn.clicked.connect(self._open_sources_history)
        source_layout.addRow('Select source from history', self.history_btn)
        return source_layout

    @pyqtSlot()
    def _open_sources_history(self):
        self.conn_win_signal.emit()

    @pyqtSlot()
    def _set_coords_line_active(self):
        line_edit_idx = self.split_check_boxes.index(self.sender())
        if self.sender().isChecked():
            self.coords_edits[line_edit_idx][0].setEnabled(True)
            self.coords_edits[line_edit_idx][1].setEnabled(True)
        else:
            self.coords_edits[line_edit_idx][0].setEnabled(False)
            self.coords_edits[line_edit_idx][1].setEnabled(False)

    def get_form(self) -> QFormLayout:
        return self.source_layout

    def get_params(self):
        return self.line_edit_param.get('sources', None)

    def get_dict(self):
        res_dict = self._create_dict()
        return res_dict

    def _create_dict(self):
        src_params = {}

        widget = self.line_edit_param['camera']
        src_params['camera'] = widget.text()

        widget = self.line_edit_param['source']
        text = widget.currentText()
        src_params['source'] = CaptureDeviceType[text].value

        widget = self.line_edit_param['apiPreference']
        text = widget.currentText()
        src_params['apiPreference'] = VideoCapture.VideoCaptureAPIs[text].name

        widget = self.line_edit_param['split']
        src_params['split'] = True if widget.isChecked() else False

        widget = self.line_edit_param['num_split']
        src_params['num_split'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['src_coords']
        src_params['src_coords'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['source_ids']
        src_params['source_ids'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['source_names']
        src_params['source_names'] = parameters_processing.process_str_list(widget.text())

        widget = self.line_edit_param['loop_play']
        src_params['loop_play'] = True if widget.isChecked() else False

        return src_params

    def closeEvent(self, event) -> None:
        if self.thread:
            self.thread.stop_thread()
            self.thread = None
        event.accept()


class SrcThread(QThread):
    update_image_signal = pyqtSignal(int, QPixmap)

    def __init__(self, params, creds, width, height):
        super().__init__()
        self.fps = 10

        self.params = params
        self.credentials = creds
        self.run_flag = False
        self.capture = None

        self.widget_width = width
        self.widget_height = height

        self._init_capture()

    def _init_capture(self):
        camera_creds = self.credentials["sources"].get(self.params["camera"], None)
        if camera_creds and (not self.params.get("username", None) or not self.params.get("password", None)):
            self.params["username"] = camera_creds["username"]
            self.params["password"] = camera_creds["password"]

        self.capture = VideoCapture()
        self.capture.set_params(**self.params)
        self.capture.init()

    def start_thread(self) -> bool:
        if not self.capture.is_opened():
            return False
        self.run_flag = True
        self.capture.start()
        self.start()
        return True

    def stop_thread(self):
        self.run_flag = False
        self.capture.stop()
        self.capture = None
        print('Test stopped')

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

    def process_image(self):
        begin_it = timer()
        frames = self.capture.get()
        for i, frame in enumerate(frames):
            qt_frame = self._convert_cv_qt(frame.image, self.widget_width, self.widget_height)
            self.update_image_signal.emit(i, qt_frame)
        end_it = timer()
        elapsed_seconds = end_it - begin_it
        return elapsed_seconds

    def _convert_cv_qt(self, cv_img, widget_width, widget_height) -> QPixmap:
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format.Format_RGB888)
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(widget_width, widget_height, Qt.AspectRatioMode.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)
