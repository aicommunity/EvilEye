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


class TrackerWidget(QWidget):
    def __init__(self, params):
        super().__init__()

        self.params = params
        self.proj_root = utils.get_project_root()

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.horizontal_layout = QHBoxLayout()
        self.horizontal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._setup_tracker_layout()
        self.setLayout(self.horizontal_layout)

    def _setup_tracker_layout(self):
        self.track_layout = self._setup_tracker_form()
        self.horizontal_layout.addLayout(self.track_layout)

    def _setup_tracker_form(self) -> QFormLayout:
        layout = QFormLayout()

        name = QLabel('Tracker Parameters')
        layout.addWidget(name)
        self.line_edit_param['trackers'] = {}

        src_ids = QLineEdit()
        src_ids.setText('[ids]')
        layout.addRow('Sources ids', src_ids)
        self.line_edit_param['trackers']['Sources ids'] = 'source_ids'

        fps = QLineEdit()
        layout.addRow('FPS', fps)
        self.line_edit_param['trackers']['FPS'] = 'fps'

        botsort_config = QCheckBox()
        layout.addRow('Configure botsort', botsort_config)
        botsort_config.checkStateChanged.connect(self._display_botsort_params)
        self._setup_botsort_params(layout)

        widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        return layout

    def _setup_botsort_params(self, layout):
        appearance_thresh = QLineEdit()
        layout.addRow('Appearance threshold', appearance_thresh)
        self.line_edit_param['trackers']['Appearance threshold'] = 'appearance_thresh'

        gmc_method = QLineEdit()
        layout.addRow('GMC method', gmc_method)
        self.line_edit_param['trackers']['GMC method'] = 'gmc_method'

        match_thresh = QLineEdit()
        layout.addRow('Match threshold', match_thresh)
        self.line_edit_param['trackers']['Match threshold'] = 'match_thresh'

        new_track_thresh = QLineEdit()
        layout.addRow('New track threshold', new_track_thresh)
        self.line_edit_param['trackers']['New track threshold'] = 'new_track_thresh'

        proximity_thresh = QLineEdit()
        layout.addRow('Proximity threshold', proximity_thresh)
        self.line_edit_param['trackers']['Proximity threshold'] = 'proximity_thresh'

        track_buffer = QLineEdit()
        layout.addRow('Track buffer', track_buffer)
        self.line_edit_param['trackers']['Track buffer'] = 'track_buffer'

        track_high_thresh = QLineEdit()
        layout.addRow('High threshold', track_high_thresh)
        self.line_edit_param['trackers']['High threshold'] = 'track_high_thresh'

        track_low_thresh = QLineEdit()
        layout.addRow('Low threshold', track_low_thresh)
        self.line_edit_param['trackers']['Low threshold'] = 'track_low_thresh'

        tracker_type = QLineEdit()
        layout.addRow('Tracker type', tracker_type)
        self.line_edit_param['trackers']['Tracker type'] = 'tracker_type'

        with_reid = QCheckBox()
        layout.addRow('With ReId', with_reid)
        self.line_edit_param['trackers']['With ReId'] = 'with_reid'

        widgets = (layout.itemAt(i).widget() for i in range(7, layout.count()))
        for widget in widgets:
            widget.setVisible(False)

    @pyqtSlot()
    def _display_botsort_params(self):
        # Индекс умножается на два из-за наличия spacers
        widgets = (self.track_layout.itemAt(i).widget() for i in range(7, self.track_layout.count()))
        if self.sender().isChecked():
            for widget in widgets:
                widget.setVisible(True)
        else:
            for widget in widgets:
                widget.setVisible(False)

    def get_form(self) -> QFormLayout:
        return self.track_layout

    def get_params(self):
        return self.line_edit_param.get('trackers', None)
