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
from evileye.visualization_modules.configurer.configurer_tabs.tracker_widget import TrackerWidget


class TrackerTab(QWidget):
    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.default_track_params = self.params[0]
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

        for params in self.params:
            new_tracker = TrackerWidget(params=params)
            self.trackers.append(new_tracker)
            self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

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
        self.duplicate_track_btn = QPushButton('Duplicate tracker')
        self.duplicate_track_btn.setMinimumWidth(200)
        self.duplicate_track_btn.clicked.connect(self._duplicate_tracker)
        self.delete_track_btn = QPushButton('Delete tracker')
        self.delete_track_btn.setMinimumWidth(200)
        self.delete_track_btn.clicked.connect(self._delete_tracker)
        self.button_layout.addWidget(self.add_track_btn)
        self.button_layout.addWidget(self.duplicate_track_btn)
        self.button_layout.addWidget(self.delete_track_btn)

        self.vertical_layout.addLayout(self.button_layout)
        self.setLayout(self.vertical_layout)

        if len(self.trackers) > 0:
            self.enable_add_tracker_button()

    @pyqtSlot()
    def _duplicate_tracker(self):
        cur_tab = self.track_tabs.currentWidget()
        new_params = copy.deepcopy(cur_tab.get_dict())
        new_tracker = TrackerWidget(new_params)
        self.trackers.append(new_tracker)
        self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

    @pyqtSlot()
    def _delete_tracker(self):
        tab_idx = self.track_tabs.currentIndex()
        self.track_tabs.tabCloseRequested.emit(tab_idx)

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
        new_params = {key: '' for key in self.default_track_params.keys()}
        new_params['botsort_cfg'] = {key: '' for key in self.default_track_params['botsort_cfg'].keys()}
        print(new_params)
        new_tracker = TrackerWidget(new_params)
        self.trackers.append(new_tracker)
        self.track_tabs.addTab(new_tracker, f'Tracker{len(self.trackers) - 1}')

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.track_tabs.count()):
            tab = self.track_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        print(forms)
        return forms

    def get_params(self):
        tracker_params = []
        for tab_idx in range(self.track_tabs.count()):
            tab = self.track_tabs.widget(tab_idx)
            tracker_params.append(tab.get_dict())
        return tracker_params
