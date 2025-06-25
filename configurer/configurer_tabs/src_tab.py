import copy
import json
import os.path
from configurer.jobs_history_journal import JobsHistory
from configurer.db_connection_window import DatabaseConnectionWindow
from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QListView,
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
from configurer.configurer_tabs.src_widget import SourceWidget
from PyQt6.QtSql import QSqlQueryModel, QSqlQuery, QSqlDatabase


class SourcesHistory(QWidget):
    def __init__(self):
        super().__init__()
        self.setMaximumWidth(400)
        sources = QListView()
        self.model = None
        self._setup_model()
        self._setup_list()
        layout = QVBoxLayout()
        layout.addWidget(self.list)
        self.setLayout(layout)

    def _setup_list(self):
        self._setup_model()

        self.list = QListView()
        self.list.setModel(self.model)

    def _setup_model(self):
        self.model = QSqlQueryModel()

        query = QSqlQuery(QSqlDatabase.database('jobs_conn'))
        query.prepare('SELECT full_address FROM camera_information;')
        query.exec()

        self.model.setQuery(query)


class SourcesTab(QWidget):
    connection_win_signal = pyqtSignal()

    def __init__(self, config_params, parent=None):
        super().__init__(parent)

        self.params = config_params
        self.default_src_params = self.params[0]
        self.config_result = copy.deepcopy(config_params)

        self.sources_tabs = QTabWidget()
        self.sources_tabs.setTabsClosable(True)
        self.sources_tabs.tabCloseRequested.connect(self._remove_tab)

        self.sources = []
        for params in self.params:
            widget = SourceWidget(params=params, parent=self)
            self.sources.append(widget)
            widget.conn_win_signal.connect(self.connection_win_signal)
            name = str(params["source_names"])
            self.sources_tabs.addTab(widget, name)

        self.src_history = None

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setLayout(self.vertical_layout)
        self.vertical_layout.addWidget(self.sources_tabs)

        self.button_layout = QHBoxLayout()
        self.button_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.add_source_btn = QPushButton('Add source')
        self.add_source_btn.setMinimumWidth(200)
        self.add_source_btn.clicked.connect(self._add_new_source)
        self.button_layout.addWidget(self.add_source_btn)
        self.vertical_layout.addLayout(self.button_layout)

    @pyqtSlot(int)
    def _remove_tab(self, idx):
        self.sources_tabs.removeTab(idx)
        self.sources.pop(idx)

    def open_src_list(self):
        active_tab = self.sources_tabs.currentWidget()
        if not self.src_history:
            self.src_history = SourcesHistory()
        for tab_idx in range(self.sources_tabs.count()):
            tab = self.sources_tabs.widget(tab_idx)
            tab.history_btn.setEnabled(True)
        active_tab.setEnabled(True)
        active_tab.show_src_history(self.src_history)

    def _create_toolbar(self):
        toolbar = QToolBar('Edit', self)
        toolbar.addAction(self.add_source)
        self.toolbar_width = toolbar.frameGeometry().width()

    def _create_actions(self):  # Создание кнопок-действий
        self.add_source = QAction('&Add source', self)
        icon_path = os.path.join(utils.get_project_root(), 'add_zone.svg')
        self.add_source.setIcon(QIcon(icon_path))

    def _connect_actions(self):
        self.add_source.triggered.connect(self._add_new_source)

    @pyqtSlot()
    def _add_new_source(self):
        new_source = SourceWidget()
        new_source.conn_win_signal.connect(self.connection_win_signal)
        self.sources.append(new_source)
        self.sources_tabs.addTab(new_source, f'Source{len(self.sources)}')

    def get_params(self):
        return self.sources[0].get_params()

    def closeEvent(self, event) -> None:
        for source in self.sources:
            source.close()
        event.accept()

    def get_forms(self) -> list[QFormLayout]:
        forms = []
        for tab_idx in range(self.sources_tabs.count()):
            tab = self.sources_tabs.widget(tab_idx)
            forms.append(tab.get_form())
        print(forms)
        return forms
