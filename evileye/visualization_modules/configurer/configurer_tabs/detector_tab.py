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
from evileye.visualization_modules.configurer.configurer_tabs.detector_widget import DetectorWidget
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCapture
from evileye.visualization_modules.configurer import parameters_processing


class DetectorTab(QWidget):
    tracker_enabled_signal = pyqtSignal()

    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.default_det_params = self.params[0]
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.buttons_layouts_number = {}

        self.detectors = []
        self.det_tabs = QTabWidget()
        self.det_tabs.setTabsClosable(True)
        self.det_tabs.tabCloseRequested.connect(self._remove_tab)

        for params in self.params:
            new_detector = DetectorWidget(params=params)
            self.detectors.append(new_detector)
            self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vertical_layout.addWidget(self.det_tabs)

        self.button_layout = QHBoxLayout()
        self.button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add_det_btn = QPushButton('Add detector')
        self.add_det_btn.setMinimumWidth(200)
        self.add_det_btn.clicked.connect(self._add_detector)
        self.duplicate_det_btn = QPushButton('Duplicate detector')
        self.duplicate_det_btn.setMinimumWidth(200)
        self.duplicate_det_btn.clicked.connect(self._duplicate_det)
        self.delete_det_btn = QPushButton('Delete detector')
        self.delete_det_btn.setMinimumWidth(200)
        self.delete_det_btn.clicked.connect(self._delete_det)
        self.button_layout.addWidget(self.add_det_btn)
        self.button_layout.addWidget(self.duplicate_det_btn)
        self.button_layout.addWidget(self.delete_det_btn)

        self.vertical_layout.addLayout(self.button_layout)
        self.setLayout(self.vertical_layout)

        if len(self.detectors) > 0:
            self.tracker_enabled_signal.emit()

    @pyqtSlot()
    def _duplicate_det(self):
        cur_tab = self.det_tabs.currentWidget()
        new_params = copy.deepcopy(cur_tab.get_dict())
        new_detector = DetectorWidget(new_params)
        self.detectors.append(new_detector)
        self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')
        if len(self.detectors) == 1:
            self.tracker_enabled_signal.emit()

    @pyqtSlot()
    def _delete_det(self):
        tab_idx = self.det_tabs.currentIndex()
        self.det_tabs.tabCloseRequested.emit(tab_idx)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.det_tabs.removeTab(idx)
        self.detectors.pop(idx)

    @pyqtSlot()
    def _add_detector(self):
        new_params = {key: '' for key in self.default_det_params.keys()}
        new_detector = DetectorWidget(new_params)
        self.detectors.append(new_detector)
        self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) - 1}')
        if len(self.detectors) == 1:
            self.tracker_enabled_signal.emit()

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.det_tabs.count()):
            tab = self.det_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        print(forms)
        return forms

    def get_params(self):
        det_params = []
        for tab_idx in range(self.det_tabs.count()):
            tab = self.det_tabs.widget(tab_idx)
            det_params.append(tab.get_dict())
        return det_params
