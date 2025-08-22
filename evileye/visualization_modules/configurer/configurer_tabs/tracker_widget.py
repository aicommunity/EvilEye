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


class TrackerWidget(QWidget):
    def __init__(self, params):
        super().__init__()

        self.params = params
        self.proj_root = utils.get_project_root()
        self.track_layout = None

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.horizontal_layout = QHBoxLayout()
        self.horizontal_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._setup_tracker_layout(self.params)
        self.setLayout(self.horizontal_layout)

    def _setup_tracker_layout(self, params):
        self.track_layout = self._setup_tracker_form(params)
        self.horizontal_layout.addLayout(self.track_layout)

    def _setup_tracker_form(self, params) -> QFormLayout:
        layout = QFormLayout()

        name = QLabel('Tracker Parameters')
        layout.addWidget(name)

        src_ids = QLineEdit()
        src_ids.setText(str(params['source_ids']))
        layout.addRow('Sources ids', src_ids)
        self.line_edit_param['source_ids'] = src_ids

        fps = QLineEdit()
        fps.setText(str(params['fps']))
        layout.addRow('FPS', fps)
        self.line_edit_param['fps'] = fps

        tracker_onnx = QLineEdit()
        tracker_onnx.setText(str(params.get('tracker_onnx', None)))
        layout.addRow('Tracker ONNX', tracker_onnx)
        self.line_edit_param['tracker_onnx'] = tracker_onnx

        botsort_params = params['botsort_cfg']
        self._setup_botsort_params(layout, botsort_params)

        widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        return layout

    def _setup_botsort_params(self, layout, params):
        appearance_thresh = QLineEdit()
        appearance_thresh.setText(str(params['appearance_thresh']))
        layout.addRow('Appearance threshold', appearance_thresh)
        self.line_edit_param['appearance_thresh'] = appearance_thresh

        gmc_method = QLineEdit()
        layout.addRow('GMC method', gmc_method)
        gmc_method.setText(str(params['gmc_method']))
        self.line_edit_param['gmc_method'] = gmc_method

        match_thresh = QLineEdit()
        layout.addRow('Match threshold', match_thresh)
        match_thresh.setText(str(params['match_thresh']))
        self.line_edit_param['match_thresh'] = match_thresh

        new_track_thresh = QLineEdit()
        layout.addRow('New track threshold', new_track_thresh)
        new_track_thresh.setText(str(params['new_track_thresh']))
        self.line_edit_param['new_track_thresh'] = new_track_thresh

        proximity_thresh = QLineEdit()
        layout.addRow('Proximity threshold', proximity_thresh)
        proximity_thresh.setText(str(params['proximity_thresh']))
        self.line_edit_param['proximity_thresh'] = proximity_thresh

        track_buffer = QLineEdit()
        layout.addRow('Track buffer', track_buffer)
        track_buffer.setText(str(params['track_buffer']))
        self.line_edit_param['track_buffer'] = track_buffer

        track_high_thresh = QLineEdit()
        layout.addRow('High threshold', track_high_thresh)
        track_high_thresh.setText(str(params['track_high_thresh']))
        self.line_edit_param['track_high_thresh'] = track_high_thresh

        track_low_thresh = QLineEdit()
        layout.addRow('Low threshold', track_low_thresh)
        track_low_thresh.setText(str(params['track_low_thresh']))
        self.line_edit_param['track_low_thresh'] = track_low_thresh

        tracker_type = QLineEdit()
        layout.addRow('Tracker type', tracker_type)
        tracker_type.setText(str(params['tracker_type']))
        self.line_edit_param['tracker_type'] = tracker_type

        with_reid = QCheckBox()
        layout.addRow('With ReId', with_reid)
        self.line_edit_param['with_reid'] = with_reid
        flag = params.get('with_reid', None)
        if flag == '' or flag is None:
            flag = False
        with_reid.setChecked(flag)
        # with_reid.setEnabled(False)
        # with_reid.checkStateChanged.connect(self._display_reid_params)

    # @pyqtSlot()
    # def _display_reid_params(self):
    #     # Индекс умножается на два из-за наличия spacers
    #     onnx_widgets = (self.track_layout.itemAt(i).widget()
    #                     for i in range(self.track_layout.count() - 2, self.track_layout.count()))
    #     if self.sender().isChecked():
    #         for widget in onnx_widgets:
    #             widget.setVisible(True)
    #     else:
    #         for widget in onnx_widgets:
    #             widget.setVisible(False)

    def get_form(self) -> QFormLayout:
        return self.track_layout

    def get_params(self):
        return self.line_edit_param.get('trackers', None)

    def get_dict(self):
        res_dict = self._create_dict()
        return res_dict

    def _create_dict(self):
        src_params = {}

        widget = self.line_edit_param['source_ids']
        src_params['source_ids'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['fps']
        src_params['fps'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['tracker_onnx']
        if widget.text() == 'None':
            src_params['inference_size'] = None
        else:
            src_params['inference_size'] = widget.text()

        botsort_params = {}

        widget = self.line_edit_param['appearance_thresh']
        botsort_params['appearance_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['gmc_method']
        botsort_params['gmc_method'] = widget.text()

        widget = self.line_edit_param['match_thresh']
        botsort_params['match_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['new_track_thresh']
        botsort_params['new_track_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['proximity_thresh']
        botsort_params['proximity_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['track_buffer']
        botsort_params['track_buffer'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['track_high_thresh']
        botsort_params['track_high_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['track_low_thresh']
        botsort_params['track_low_thresh'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['tracker_type']
        botsort_params['tracker_type'] = widget.text()

        widget = self.line_edit_param['with_reid']
        botsort_params['with_reid'] = True if widget.isChecked() else False

        src_params['botsort_cfg'] = botsort_params
        return src_params
