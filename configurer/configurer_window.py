import copy
import json
import os.path
import multiprocessing
from configurer.jobs_history_journal import JobsHistory
from configurer.db_connection_window import DatabaseConnectionWindow
from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QTextEdit,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
)
from utils import utils
from PyQt6.QtGui import QIcon
from PyQt6.QtGui import QAction
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from capture.video_capture_base import CaptureDeviceType
from capture import VideoCapture
import configurer.parameters_processing
from configurer.configurer_tabs import src_tab, detector_tab, handler_tab, visualizer_tab, database_tab, tracker_tab, events_tab
import visualization


class SaveWindow(QWidget):
    save_params_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.h_layout = QHBoxLayout()
        self.save_button = QPushButton('Save parameters', self)
        self.save_button.clicked.connect(self._save_data)
        self.file_name = QLabel('Enter file name')
        self.file_name_edit = QTextEdit()
        self.file_name_edit.setText('.json')
        self.file_name_edit.setFixedHeight(self.save_button.geometry().height())
        self.h_layout.addWidget(self.file_name_edit)
        self.h_layout.addWidget(self.save_button)
        self.setLayout(self.h_layout)

    @pyqtSlot()
    def _save_data(self):
        file_name = self.file_name_edit.toPlainText()
        if not file_name.strip('.json'):
            file_name = 'temp.json'
        self.save_params_signal.emit(file_name)
        self.close()


class ConfigurerMainWindow(QMainWindow):
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int)

    def __init__(self, win_width, win_height):
        super().__init__()
        self.setWindowTitle("EvilEye Configurer")
        self.resize(win_width, win_height)

        file_path = 'configurer/initial_config.json'
        full_path = os.path.join(utils.get_project_root(), file_path)
        with open(full_path, 'r+') as params_file:
            config_params = json.load(params_file)

        self.params = config_params
        self.default_src_params = self.params['sources'][0]
        self.default_det_params = self.params['detectors'][0]
        self.default_track_params = self.params['trackers'][0]
        self.default_vis_params = self.params['visualizer']
        self.default_db_params = self.params['database']
        self.default_events_params = self.params['events_detectors']
        self.default_handler_params = self.params['objects_handler']
        self.config_result = copy.deepcopy(config_params)

        self.src_hist_clicked = False
        self.jobs_hist_clicked = False

        self.proj_root = utils.get_project_root()
        self.hor_layouts = {}
        self.det_button = None
        self.track_buttons = []
        self.split_check_boxes = []
        self.botsort_check_boxes = []
        self.coords_edits = []
        self.src_counter = 0
        self.jobs_history = None
        self.db_window = DatabaseConnectionWindow()
        self.db_window.database_connection_signal.connect(self._open_history)
        self.db_window.setVisible(False)

        self.save_win = SaveWindow()
        self.save_win.save_params_signal.connect(self._save_params)

        self.tab_params = {}  # Словарь для сопоставления полей интерфейса с полями json-файла

        self._setup_tabs()

        self.main_widget = QWidget()
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.tabs)
        self._create_actions()
        self._connect_actions()
        self.menu_height = 0
        self._create_menu_bar()

        self.run_flag = False

        self.toolbar_width = 0
        self._create_toolbar()

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setCentralWidget(self.scroll_area)
        self.result_filename = None
        multiprocessing.set_start_method('spawn')

    def _setup_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.addTab(src_tab.SourcesTab(self.params, parent=self), 'Sources')
        self.tabs.addTab(detector_tab.DetectorTab(self.params), 'Detectors')
        self.tabs.addTab(tracker_tab.TrackerTab(self.params), 'Trackers')
        self.tabs.addTab(handler_tab.HandlerTab(self.params), 'Objects handler')
        self.tabs.addTab(database_tab.DatabaseTab(self.params), 'Database')
        self.tabs.addTab(visualizer_tab.VisualizerTab(self.params), 'Visualizer')
        self.tabs.addTab(events_tab.EventsTab(self.params), 'Events')
        self.sections = ['sources', 'detectors', 'trackers', 'objects_handler',
                         'database', 'visualizer', 'events_detectors']

        source_tab = self.tabs.widget(0)
        source_tab.connection_win_signal.connect(self._connect_to_db)
        det_tab = self.tabs.widget(1)
        track_tab = self.tabs.widget(2)
        det_tab.tracker_enabled_signal.connect(track_tab.enable_add_tracker_button)

        self.tab_params['sources'] = self.tabs.widget(0)
        self.tab_params['detectors'] = self.tabs.widget(1)
        self.tab_params['trackers'] = self.tabs.widget(2)
        self.tab_params['objects_handler'] = self.tabs.widget(3)
        self.tab_params['database'] = self.tabs.widget(4)
        self.tab_params['visualizer'] = self.tabs.widget(5)
        self.tab_params['events_detectors'] = self.tabs.widget(6)

    def _create_menu_bar(self):
        menu = self.menuBar()
        edit_menu = QMenu('&Edit', self)
        open_menu = QMenu('&Open', self)
        run_menu = QMenu('&Run', self)
        menu.addMenu(open_menu)
        menu.addMenu(edit_menu)
        menu.addMenu(run_menu)
        edit_menu.addAction(self.save_params)
        open_menu.addAction(self.open_jobs_history)
        run_menu.addAction(self.start_app)
        self.menu_height = edit_menu.frameGeometry().height()

    def _create_toolbar(self):
        toolbar = QToolBar('Edit', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, toolbar)
        toolbar.addAction(self.save_params)
        toolbar.addAction(self.open_jobs_history)
        toolbar.addAction(self.start_app)
        self.toolbar_width = toolbar.frameGeometry().width()

    def _create_actions(self):  # Создание кнопок-действий
        self.save_params = QAction('&Save parameters', self)
        self.save_params.setIcon(QIcon('save_icon.svg'))
        self.open_jobs_history = QAction('&Open history', self)
        self.start_app = QAction('&Run app', self)
        self.start_app.setIcon(QIcon('run_app.svg'))
        icon_path = os.path.join(utils.get_project_root(), 'journal.svg')
        self.open_jobs_history.setIcon(QIcon(icon_path))

    def _connect_actions(self):
        self.save_params.triggered.connect(self._open_save_win)
        self.open_jobs_history.triggered.connect(self._connect_to_db)
        self.start_app.triggered.connect(self._prepare_running)

    @pyqtSlot()
    def _prepare_running(self):
        self.run_flag = True
        self._open_save_win()

    def _run_app(self):
        self.new_process = multiprocessing.Process(target=visualization.start_app, args=(self.result_filename,))
        self.new_process.start()
        self.new_process.join()

    @pyqtSlot()
    def _open_save_win(self):
        self.save_win.show()

    @pyqtSlot(str)
    def _save_params(self, file_name):
        self._process_params_strings()
        self.result_filename = os.path.join(utils.get_project_root(), file_name)
        with open(self.result_filename, 'w') as file:
            json.dump(self.config_result, file, indent=4)

        if self.run_flag:
            self.save_win.close()
            self._run_app()

    @pyqtSlot()
    def _connect_to_db(self):
        sender = self.sender()
        if isinstance(sender, QAction):
            self.jobs_hist_clicked = True
            self.src_hist_clicked = False
            if self.db_window.is_connected():
                self._open_history()
            else:
                if self.db_window.isVisible():
                    self.db_window.setVisible(False)
                else:
                    self.db_window.setVisible(True)
        else:
            self.src_hist_clicked = True
            self.jobs_hist_clicked = False
            if self.db_window.is_connected():
                self.tabs.widget(0).open_src_list()
            else:
                if self.db_window.isVisible():
                    self.db_window.setVisible(False)
                else:
                    self.db_window.setVisible(True)

    @pyqtSlot()
    def _open_history(self):
        if self.jobs_hist_clicked:
            if not self.jobs_history:
                self.jobs_history = JobsHistory()
                self.jobs_history.setVisible(False)

            if self.jobs_history.isVisible():
                self.jobs_history.setVisible(False)
            else:
                self.jobs_history.setVisible(True)

        if self.src_hist_clicked:
            self.tabs.widget(0).open_src_list()

    def _process_params_strings(self):
        for section in self.sections:
            match section:
                case 'sources':
                    src_config = configurer.parameters_processing.process_src_params(
                        self.tab_params['sources'].get_forms(), self.tab_params['sources'].get_params())
                    self._rewrite_config('sources', self.default_src_params, src_config)
                case 'detectors':
                    det_config = configurer.parameters_processing.process_detector_params(
                        self.tab_params['detectors'].get_forms(), self.tab_params['detectors'].get_params())
                    self._rewrite_config('detectors', self.default_det_params, det_config)
                case 'trackers':
                    track_config = configurer.parameters_processing.process_tracker_params(
                        self.tab_params['trackers'].get_forms(), self.tab_params['trackers'].get_params())
                    self._rewrite_config('trackers', self.default_track_params, track_config)
                case 'visualizer':
                    handler_config = configurer.parameters_processing.process_visualizer_params(
                        self.tab_params['visualizer'].get_forms(), self.tab_params['visualizer'].get_params())
                    self._rewrite_config('visualizer', self.default_vis_params, handler_config)
                case 'database':
                    db_config = configurer.parameters_processing.process_database_params(
                        self.tab_params['database'].get_forms(), self.tab_params['database'].get_params())
                    self._rewrite_config('database', self.default_db_params, db_config)
                case 'objects_handler':
                    handler_config = configurer.parameters_processing.process_handler_params(
                        self.tab_params['objects_handler'].get_forms(), self.tab_params['objects_handler'].get_params())
                    self._rewrite_config('objects_handler', self.default_handler_params, handler_config)
                case 'events_detectors':
                    events_config = configurer.parameters_processing.process_events_params(
                        self.tab_params['events_detectors'].get_forms(), self.tab_params['events_detectors'].get_params())
                    self._rewrite_config('events_detectors', self.default_events_params, events_config)

    def _rewrite_config(self, section_name, default_params, new_params):
        if not default_params:
            self.config_result[section_name] = new_params
        else:
            if isinstance(new_params, list):
                if not new_params:
                    new_params = []
                else:
                    for instance_params in new_params:
                        for key in default_params:
                            if key not in instance_params:
                                instance_params[key] = default_params[key]
            elif isinstance(new_params, dict):
                if not new_params:
                    new_params = {}
                else:
                    for key in default_params:
                        if key not in new_params or not new_params[key]:
                            new_params[key] = default_params[key]
                        if isinstance(new_params[key], dict):
                            print(default_params[key])
                            for inner_key in default_params[key]:
                                if inner_key not in new_params[key] or not new_params[key][inner_key]:
                                    new_params[key][inner_key] = default_params[key][inner_key]
            self.config_result[section_name] = new_params

    def closeEvent(self, event):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        self.db_window.close()
        QApplication.closeAllWindows()
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    a = ConfigurerMainWindow(1280, 720)
    a.show()
    ret = app.exec()
    sys.exit(ret)
