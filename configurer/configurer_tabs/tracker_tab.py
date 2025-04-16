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
from configurer.configurer_tabs.tracker_widget import TrackerWidget


class TrackerTab(QWidget):
    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.default_track_params = self.params['trackers'][0]
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = []
        self.layout_check_boxes = {}
        self.botsort_check_boxes = []
        self.src_counter = 0
        self.buttons_layouts_number = {}
        self.widgets_counter = 0
        self.layouts_counter = 0

        self.trackers = []
        self.track_tabs = QTabWidget()
        self.track_tabs.setTabsClosable(True)
        self.track_tabs.tabCloseRequested.connect(self._remove_tab)

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.label = QLabel('To add a tracker you must add a detector first')
        self.vertical_layout.addWidget(self.label)

        self.button_layout = QHBoxLayout()
        self.button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add_track_btn = QPushButton('Add tracker')
        self.add_track_btn.setMinimumWidth(200)
        self.add_track_btn.setEnabled(False)
        self.add_track_btn.clicked.connect(self._add_tracker)
        self.button_layout.addWidget(self.add_track_btn)

        self.vertical_layout.addLayout(self.button_layout)
        self.setLayout(self.vertical_layout)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.track_tabs.removeTab(idx)
        self.trackers.pop(idx)

    @pyqtSlot()
    def enable_add_tracker_button(self):
        self.add_track_btn.setEnabled(True)
        self.label.hide()
        self.vertical_layout.removeWidget(self.label)
        self.vertical_layout.insertWidget(0, self.track_tabs)

    @pyqtSlot()
    def _add_tracker(self):
        new_tracker = TrackerWidget()
        self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) + 1}')
        self.trackers.append(new_tracker)

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.track_tabs.count()):
            tab = self.track_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        print(forms)
        return forms

    def get_params(self):
        if self.trackers:
            return self.trackers[0].get_params()
        return None
