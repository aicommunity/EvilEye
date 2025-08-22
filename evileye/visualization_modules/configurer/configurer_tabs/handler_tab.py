import copy
try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
        QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem,
        QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5
from evileye.utils import utils
from evileye.visualization_modules.configurer import parameters_processing


class HandlerTab(QWidget):
    def __init__(self, config_params, database_params):
        super().__init__()

        self.params = config_params
        self.database_params = database_params
        self.default_src_params = self.database_params['database']
        self.config_result = copy.deepcopy(config_params)

        self.proj_root = utils.get_project_root()
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.src_counter = 0

        self.line_edit_param = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._setup_layout()
        self.setLayout(self.vertical_layout)

    def _setup_layout(self):
        self.vertical_layout.setContentsMargins(10, 10, 10, 10)

        handler_layout = self._setup_handler_form()
        self.vertical_layout.addLayout(handler_layout)

    def _setup_handler_form(self):
        layout = QFormLayout()

        name = QLabel('Handler Parameters')
        layout.addWidget(name)

        history_len = QLineEdit()
        history_len.setText('30')
        layout.addRow('History length', history_len)
        self.line_edit_param['history_len'] = history_len

        lost_store_time_secs = QLineEdit()
        lost_store_time_secs.setText('60')
        layout.addRow('Lost objects store time', lost_store_time_secs)
        self.line_edit_param['lost_store_time_secs'] = lost_store_time_secs

        lost_thresh = QLineEdit()
        lost_thresh.setText('5')
        layout.addRow('Lost threshold', lost_thresh)
        self.line_edit_param['lost_thresh'] = lost_thresh

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
        hand_params = {}

        widget = self.line_edit_param['history_len']
        hand_params['history_len'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['lost_store_time_secs']
        hand_params['lost_store_time_secs'] = parameters_processing.process_numeric_types(widget.text())

        widget = self.line_edit_param['lost_thresh']
        hand_params['lost_thresh'] = parameters_processing.process_numeric_types(widget.text())

        return hand_params
