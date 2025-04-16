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
        self.line_edit_param['visualizer'] = {}

        num_width = QLineEdit()
        layout.addRow('Number of cameras in width', num_width)
        self.line_edit_param['visualizer']['Number of cameras in width'] = 'num_width'

        num_height = QLineEdit()
        layout.addRow('Number of cameras in height', num_height)
        self.line_edit_param['visualizer']['Number of cameras in height'] = 'num_height'

        visual_buffer = QLineEdit()
        layout.addRow('Visual buffer size', visual_buffer)
        self.line_edit_param['visualizer']['Visual buffer size'] = 'visual_buffer_num_frames'

        source_ids = QLineEdit()
        source_ids.setText('[Sources]')
        layout.addRow('Visualized sources', source_ids)
        self.line_edit_param['visualizer']['Visualized sources'] = 'source_ids'

        fps_sources = QLineEdit()
        fps_sources.setText('[Sources fps]')
        layout.addRow('Sources fps', fps_sources)
        self.line_edit_param['visualizer']['Sources fps'] = 'fps'

        gui_enabled = QCheckBox()
        layout.addRow('GUI Enabled', gui_enabled)
        self.line_edit_param['visualizer']['GUI Enabled'] = 'gui_enabled'

        show_debug_info = QCheckBox()
        layout.addRow('Show debug information', show_debug_info)
        self.line_edit_param['visualizer']['Show debug information'] = 'show_debug_info'

        objects_journal_enabled = QCheckBox()
        layout.addRow('Objects journal enabled', objects_journal_enabled)
        self.line_edit_param['visualizer']['Objects journal enabled'] = 'objects_journal_enabled'

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
        return self.line_edit_param['visualizer']
