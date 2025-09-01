import copy
import json
import os.path
import multiprocessing
from .jobs_history_journal import JobsHistory
from .db_connection_window import DatabaseConnectionWindow

try:
    from PyQt6 import QtGui
    from PyQt6.QtGui import QIcon
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt6.QtSql import QSqlDatabase
    from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea, QMessageBox,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QTextEdit,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtGui import QIcon
    from PyQt5.QtGui import QAction
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    from PyQt5.QtSql import QSqlDatabase
    from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QScrollArea, QMessageBox,
    QSizePolicy, QToolBar, QComboBox, QFormLayout, QSpacerItem, QTextEdit,
    QMenu, QMainWindow, QApplication, QCheckBox, QPushButton, QTabWidget
    )
    pyqt_version = 5


from ...utils import utils
from .configurer_tabs import src_tab, detector_tab, handler_tab, visualizer_tab, database_tab, tracker_tab, events_tab
from ... import process


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

    def __init__(self, config_file_name, win_width, win_height):
        super().__init__()
        self.config_file_name = config_file_name
        self.setWindowTitle("EvilEye Configurer")
        self.resize(win_width, win_height)

        self.is_db_connected = False

        file_path = self.config_file_name  # 'configurer/initial_config.json'
        full_path = os.path.join(utils.get_project_root(), file_path)
        with open(full_path, 'r+') as params_file:
            config_params = json.load(params_file)

        with open(os.path.join(utils.get_project_root(), "evileye", "database_config.json"), 'r+') as database_config_file:
            database_params = json.load(database_config_file)

        try:
            with open("credentials.json") as creds_file:
                self.credentials = json.load(creds_file)
        except FileNotFoundError as ex:
            pass

        database_creds = self.credentials.get("database", None)
        if not database_creds:
            database_creds = dict()

        try:
            with open(os.path.join(utils.get_project_root(), "evileye", "database_config.json")) as data_config_file:
                self.database_config = json.load(data_config_file)
        except FileNotFoundError as ex:
            self.database_config = dict()
            self.database_config["database"] = dict()

        database_creds["user_name"] = database_creds.get("user_name", "evil_eye_user")
        database_creds["password"] = database_creds.get("password", "")
        database_creds["database_name"] = database_creds.get("database_name", "evil_eye_db")
        database_creds["host_name"] = database_creds.get("host_name", "localhost")
        database_creds["port"] = database_creds.get("port", 5432)
        database_creds["admin_user_name"] = database_creds.get("admin_user_name", "postgres")
        database_creds["admin_password"] = database_creds.get("admin_password", "")

        self.database_config["database"]["user_name"] = self.database_config["database"].get("user_name", database_creds["user_name"])
        self.database_config["database"]["password"] = self.database_config["database"].get("password", database_creds["password"])
        self.database_config["database"]["database_name"] = self.database_config["database"].get("database_name", database_creds["database_name"])
        self.database_config["database"]["host_name"] = self.database_config["database"].get("host_name", database_creds["host_name"])
        self.database_config["database"]["port"] = self.database_config["database"].get("port", database_creds["port"])
        self.database_config["database"]["admin_user_name"] = self.database_config["database"].get("admin_user_name", database_creds["admin_user_name"])
        self.database_config["database"]["admin_password"] = self.database_config["database"].get("admin_password", database_creds["admin_password"])

        self.params = config_params
        self.default_src_params = self.params['sources'][0]
        self.default_det_params = self.params['detectors'][0]
        self.default_track_params = self.params['trackers'][0]
        self.default_vis_params = self.params['visualizer']
        self.default_db_params = self.database_config['database']
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
        # self.db_window = DatabaseConnectionWindow(self.database_config)
        # self.db_window.database_connection_signal.connect(self._open_history)
        # self.db_window.setVisible(False)

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
        self._connect_to_db()

        self.vertical_layout = QVBoxLayout()
        self.vertical_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.setCentralWidget(self.scroll_area)
        self.result_filename = None
        multiprocessing.set_start_method('spawn')

    def _setup_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.addTab(src_tab.SourcesTab(self.params['sources'], self.credentials, parent=self), 'Sources')
        self.tabs.addTab(detector_tab.DetectorTab(self.params['detectors']), 'Detectors')
        self.tabs.addTab(tracker_tab.TrackerTab(self.params['trackers']), 'Trackers')
        self.tabs.addTab(handler_tab.HandlerTab(self.params, self.database_config), 'Objects handler')
        self.tabs.addTab(database_tab.DatabaseTab(self.params, self.database_config), 'Database')
        self.tabs.addTab(visualizer_tab.VisualizerTab(self.params), 'Visualizer')
        self.tabs.addTab(events_tab.EventsTab(self.params), 'Events')
        self.sections = ['sources', 'detectors', 'trackers', 'objects_handler',
                         'database', 'visualizer', 'events_detectors']

        source_tab = self.tabs.widget(0)
        source_tab.connection_win_signal.connect(self._check_db_connection)
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
        self.save_params.setIcon(QIcon(os.path.join(utils.get_project_root(), 'icons', 'save_icon.svg')))
        self.open_jobs_history = QAction('&Open history', self)
        self.start_app = QAction('&Run app', self)
        self.start_app.setIcon(QIcon(os.path.join(utils.get_project_root(), 'icons', 'run_app.svg')))
        icon_path = os.path.join(utils.get_project_root(), 'icons', 'journal.svg')
        self.open_jobs_history.setIcon(QIcon(icon_path))

    def _connect_actions(self):
        self.save_params.triggered.connect(self._open_save_win)
        self.open_jobs_history.triggered.connect(self._check_db_connection)
        self.start_app.triggered.connect(self._prepare_running)

    @pyqtSlot()
    def _prepare_running(self):
        self.run_flag = True
        self._open_save_win()

    def _run_app(self):
        self.new_process = multiprocessing.Process(target=process.start_app, args=(self.result_filename,))
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
    def _check_db_connection(self):
        sender = self.sender()
        if isinstance(sender, QAction):
            self.jobs_hist_clicked = True
            self.src_hist_clicked = False
            if self.is_db_connected:
                self._open_history()
            else:
                self._connect_to_db()
                # if self.db_window.isVisible():
                #     self.db_window.setVisible(False)
                # else:
                #     self.db_window.setVisible(True)
        else:
            self.src_hist_clicked = True
            self.jobs_hist_clicked = False
            if self.is_db_connected:
                self.tabs.widget(0).open_src_list()
            else:
                self._connect_to_db()
                # if self.db_window.isVisible():
                #     self.db_window.setVisible(False)
                # else:
                #     self.db_window.setVisible(True)

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
        configs = []
        src_config = self.tab_params['sources'].get_params()
        configs.append(('sources', src_config))
        det_config = self.tab_params['detectors'].get_params()
        configs.append(('detectors', det_config))
        track_config = self.tab_params['trackers'].get_params()
        configs.append(('trackers', track_config))
        vis_config = self.tab_params['visualizer'].get_params()
        configs.append(('visualizer', vis_config))
        handler_config = self.tab_params['objects_handler'].get_params()
        configs.append(('objects_handler', handler_config))
        events_config = self.tab_params['events_detectors'].get_params()
        configs.append(('events_detectors', events_config))
        self._create_resulting_config(configs, self.params)

    def _create_resulting_config(self, configs, default_config):
        for section_config in configs:
            section_name = section_config[0]
            section_params = section_config[1]
            self.config_result[section_name] = section_params

    def _connect_to_db(self):
        db_params = self.database_config['database']
        db = QSqlDatabase.addDatabase("QPSQL", 'jobs_conn')
        db.setHostName(db_params['host_name'])
        db.setDatabaseName(db_params['database_name'])
        db.setUserName(db_params['user_name'])
        db.setPassword(db_params['password'])
        db.setPort(db_params['port'])
        if not db.open():
            QMessageBox.critical(
                None,
                "Connection error",
                str(db.lastError().text()),
            )
            self.is_db_connected = False
        else:
            self.is_db_connected = True

    def closeEvent(self, event):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        # self.db_window.close()
        print('DB jobs_conn removed')
        QSqlDatabase.removeDatabase('jobs_conn')
        QApplication.closeAllWindows()
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
