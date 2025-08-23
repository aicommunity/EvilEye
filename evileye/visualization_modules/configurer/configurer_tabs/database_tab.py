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
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
import sys
from evileye.capture.video_capture_base import CaptureDeviceType
from evileye.capture import VideoCapture
from evileye.visualization_modules.configurer import parameters_processing


class DatabaseTab(QWidget):
    def __init__(self, config_params, database_params):
        super().__init__()

        self.params = config_params
        self.database_params = database_params
        self.default_src_params = self.database_params['database']
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

        db_layout = self._setup_database_form()
        self.vertical_layout.addLayout(db_layout)

    def _setup_database_form(self):
        layout = QFormLayout()

        name = QLabel('Database Parameters')
        layout.addWidget(name)
        self.line_edit_param['database'] = {}

        user_name = QLineEdit()
        layout.addRow('Username', user_name)
        self.line_edit_param['database']['Username'] = 'user_name'

        password = QLineEdit()
        layout.addRow('Password', password)
        self.line_edit_param['database']['Password'] = 'password'

        db_name = QLineEdit()
        layout.addRow('DB name', db_name)
        self.line_edit_param['database']['DB name'] = 'database_name'

        host_name = QLineEdit()
        layout.addRow('Host name', host_name)
        self.line_edit_param['database']['Host name'] = 'host_name'

        port = QLineEdit()
        layout.addRow('Port', port)
        self.line_edit_param['database']['Port'] = 'port'

        # Admin credentials section
        admin_label = QLabel('Admin Credentials (for database creation)')
        admin_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addRow(admin_label)

        admin_user_name = QLineEdit()
        admin_user_name.setText('postgres')
        layout.addRow('Admin username', admin_user_name)
        self.line_edit_param['database']['Admin username'] = 'admin_user_name'

        admin_password = QLineEdit()
        admin_password.setEchoMode(QLineEdit.EchoMode.Password)
        layout.addRow('Admin password', admin_password)
        self.line_edit_param['database']['Admin password'] = 'admin_password'

        # Other settings section
        other_label = QLabel('Other Settings')
        other_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addRow(other_label)

        image_dir = QLineEdit()
        layout.addRow('Image directory', image_dir)
        self.line_edit_param['database']['Image directory'] = 'image_dir'

        preview_width = QLineEdit()
        preview_width.setText('300')
        layout.addRow('Preview width', preview_width)
        self.line_edit_param['database']['Preview width'] = 'preview_width'

        preview_height = QLineEdit()
        preview_height.setText('150')
        layout.addRow('Preview height', preview_height)
        self.line_edit_param['database']['Preview height'] = 'preview_height'

        create_new_project = QCheckBox()
        layout.addRow('Create new project', create_new_project)
        self.line_edit_param['database']['Create new project'] = 'create_new_project'

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
        return self.line_edit_param['database']
