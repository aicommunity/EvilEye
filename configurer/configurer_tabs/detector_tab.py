import copy
import json
import os.path
from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
)
from configurer.configurer_tabs.detector_widget import DetectorWidget
from utils import utils
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QAction
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from capture.video_capture_base import CaptureDeviceType
from capture import VideoCapture
from configurer import parameters_processing


class DetectorTab(QWidget):
    tracker_enabled_signal = pyqtSignal()

    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.default_src_params = self.params['detectors'][0]
        self.default_track_params = self.params['trackers'][0]
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.buttons_layouts_number = {}

        self.detectors = []
        self.det_tabs = QTabWidget()
        self.det_tabs.setTabsClosable(True)
        self.det_tabs.tabCloseRequested.connect(self._remove_tab)

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vertical_layout.addWidget(self.det_tabs)

        self.button_layout = QHBoxLayout()
        self.button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add_det_btn = QPushButton('Add detector')
        self.add_det_btn.setMinimumWidth(200)
        self.add_det_btn.clicked.connect(self._add_detector)
        self.button_layout.addWidget(self.add_det_btn)

        self.vertical_layout.addLayout(self.button_layout)
        self.setLayout(self.vertical_layout)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.det_tabs.removeTab(idx)
        self.detectors.pop(idx)

    @pyqtSlot()
    def _add_detector(self):
        new_detector = DetectorWidget()
        self.det_tabs.addTab(new_detector, f'Detector{len(self.detectors) + 1}')
        if not self.detectors:
            self.tracker_enabled_signal.emit()
        self.detectors.append(new_detector)

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.det_tabs.count()):
            tab = self.det_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        print(forms)
        return forms

    def get_params(self):
        if self.detectors:
            return self.detectors[0].get_params()
        return None
