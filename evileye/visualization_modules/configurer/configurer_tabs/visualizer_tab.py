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


class VisualizerTab(QWidget):
    def __init__(self, config_params):
        super().__init__()

        self.params = config_params
        self.default_src_params = self.params['visualizer']
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.hor_layouts = {}
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.src_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.vertical_layout = QVBoxLayout()
        # self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_layout()
        self.setLayout(self.vertical_layout)

    def _setup_layout(self):
        self.vertical_layout.setContentsMargins(10, 10, 10, 10)

        visualizer_layout = self._setup_visualizer_form()
        self.vertical_layout.addLayout(visualizer_layout)

    def _setup_visualizer_form(self):
        layout = QFormLayout()

        name = QLabel('Visualizer Parameters')
        layout.addWidget(name)

        num_width = QLineEdit()
        layout.addRow('Number of cameras in width', num_width)
        self.line_edit_param['num_width'] = num_width

        num_height = QLineEdit()
        layout.addRow('Number of cameras in height', num_height)
        self.line_edit_param['num_height'] = num_height

        visual_buffer = QLineEdit()
        layout.addRow('Visual buffer size', visual_buffer)
        self.line_edit_param['visual_buffer_num_frames'] = visual_buffer

        source_ids = QLineEdit()
        source_ids.setText('[Sources]')
        layout.addRow('Visualized sources', source_ids)
        self.line_edit_param['source_ids'] = source_ids

        fps_sources = QLineEdit()
        fps_sources.setText('[Sources fps]')
        layout.addRow('Sources fps', fps_sources)
        self.line_edit_param['fps'] = fps_sources

        gui_enabled = QCheckBox()
        layout.addRow('GUI Enabled', gui_enabled)
        self.line_edit_param['gui_enabled'] = gui_enabled

        show_debug_info = QCheckBox()
        layout.addRow('Show debug information', show_debug_info)
        self.line_edit_param['show_debug_info'] = show_debug_info

        objects_journal_enabled = QCheckBox()
        layout.addRow('Objects journal enabled', objects_journal_enabled)
        self.line_edit_param['objects_journal_enabled'] = objects_journal_enabled

        widgets = (layout.itemAt(i).widget() for i in range(layout.count()))
        for widget in widgets:
            widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            widget.setMinimumWidth(200)
        return layout

    def get_forms(self) -> list[QFormLayout]:
        form_layouts = []
        forms = [form for i in range(self.vertical_layout.count()) if isinstance(form := self.vertical_layout.itemAt(i), QFormLayout)]
        form_layouts.extend(forms)
        return form_layouts

    def get_params(self):
        res_dict = self._create_dict()
        return res_dict

    def _create_dict(self):
        vis_params = {}

        widget = self.line_edit_param['num_width']
        vis_params['num_width'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['num_height']
        vis_params['num_height'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['visual_buffer_num_frames']
        vis_params['visual_buffer_num_frames'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['source_ids']
        vis_params['source_ids'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['fps']
        vis_params['fps'] = parameters_processing.process_numeric_lists(widget.text())

        widget = self.line_edit_param['gui_enabled']
        vis_params['gui_enabled'] = True if widget.isChecked() else False

        widget = self.line_edit_param['show_debug_info']
        vis_params['show_debug_info'] = True if widget.isChecked() else False

        widget = self.line_edit_param['objects_journal_enabled']
        vis_params['objects_journal_enabled'] = True if widget.isChecked() else False

        return vis_params
