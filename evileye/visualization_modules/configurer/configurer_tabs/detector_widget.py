import copy
import json
import os.path
try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    from PyQt6.QtGui import QIcon
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    from PyQt5.QtGui import QIcon
    from PyQt5.QtGui import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5

from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCapture
from evileye.visualization_modules.configurer import parameters_processing


class DetectorWidget(QWidget):
    def __init__(self, params):
        super().__init__()

        self.params = params
        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.split_check_boxes = []
        #self.botsort_check_boxes = []
        #self.coords_edits = []
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.layouts_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.horizontal_layout = QHBoxLayout()
        self.horizontal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._setup_detector_layout(self.params)
        self.setLayout(self.horizontal_layout)

    def _setup_detector_layout(self, params):
        self.det_layout = self._setup_detector_form(params)
        self.horizontal_layout.addLayout(self.det_layout)

    def _setup_detector_form(self, params) -> QFormLayout:
        layout = QFormLayout()

        name = QLabel('Detector Parameters')
        layout.addWidget(name)
        self.line_edit_param = {}

        src_ids = QLineEdit()
        src_ids.setText(str(params['source_ids']))
        layout.addRow('Sources ids', src_ids)
        self.line_edit_param['source_ids'] = src_ids

        model = QLineEdit()
        layout.addRow('Model', model)
        model.setText(params['model'])
        self.line_edit_param['model'] = model

        inf_size = QLineEdit()
        inf_size.setText(str(params['inference_size']))
        layout.addRow('Inference size', inf_size)
        self.line_edit_param['inference_size'] = inf_size

        conf = QLineEdit()
        layout.addRow('Confidence', conf)
        conf.setText(str(params['conf']))
        self.line_edit_param['conf'] = conf

        classes = QLineEdit()
        classes.setText(str(params['classes']))
        layout.addRow('Classes', classes)
        self.line_edit_param['classes'] = classes

        num_det_threads = QLineEdit()
        num_det_threads.setText(str(params['num_detection_threads']))
        layout.addRow('Number of threads', num_det_threads)
        self.line_edit_param['num_detection_threads'] = num_det_threads

        roi = QLineEdit()
        roi.setText(str(params['roi']))
        layout.addRow('ROI', roi)
        self.line_edit_param['roi'] = roi

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

    def get_dict(self):
        res_dict = self._create_dict()
        return res_dict

    def _create_dict(self):
        src_params = {}

        widget = self.line_edit_param['source_ids']
        src_params['source_ids'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['model']
        src_params['model'] = widget.text()

        widget = self.line_edit_param['inference_size']
        src_params['inference_size'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['conf']
        src_params['conf'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['classes']
        src_params['classes'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['num_detection_threads']
        src_params['num_detection_threads'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['roi']
        src_params['roi'] = parameters_processing.process_numeric_lists(widget.text())
        return src_params
