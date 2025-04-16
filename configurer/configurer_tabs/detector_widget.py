import copy
import json
import os.path
from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
)
from utils import utils
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QAction
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from capture.video_capture_base import CaptureDeviceType
from capture import VideoCapture
from configurer import parameters_processing


class DetectorWidget(QWidget):
    def __init__(self):
        super().__init__()

        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.layouts_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.horizontal_layout = QHBoxLayout()
        self.horizontal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._setup_detector_layout()
        self.setLayout(self.horizontal_layout)

    def _setup_detector_layout(self):
        self.det_layout = self._setup_detector_form()
        self.horizontal_layout.addLayout(self.det_layout)

    def _setup_detector_form(self) -> QFormLayout:
        layout = QFormLayout()

        name = QLabel('Detector Parameters')
        layout.addWidget(name)
        self.line_edit_param['detectors'] = {}

        src_ids = QLineEdit()
        src_ids.setText('[ids]')
        layout.addRow('Sources ids', src_ids)
        self.line_edit_param['detectors']['Sources ids'] = 'source_ids'

        model = QLineEdit()
        layout.addRow('Model', model)
        self.line_edit_param['detectors']['Model'] = 'model'

        inf_size = QLineEdit()
        layout.addRow('Inference size', inf_size)
        self.line_edit_param['detectors']['Inference size'] = 'inference_size'

        conf = QLineEdit()
        layout.addRow('Confidence', conf)
        self.line_edit_param['detectors']['Confidence'] = 'conf'

        classes = QLineEdit()
        classes.setText('[classes(int)]')
        layout.addRow('Classes', classes)
        self.line_edit_param['detectors']['Classes'] = 'classes'

        num_det_threads = QLineEdit()
        layout.addRow('Number of threads', num_det_threads)
        self.line_edit_param['detectors']['Number of threads'] = 'num_detection_threads'

        roi = QLineEdit()
        roi.setText('[[[roi1_coords], [roi2_coords]]]')
        layout.addRow('ROI', roi)
        self.line_edit_param['detectors']['ROI'] = 'roi'

        widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        self.widgets_counter += 1
        return layout

    def get_form(self) -> QFormLayout:
        return self.det_layout

    def get_params(self):
        return self.line_edit_param.get('detectors', None)
