import copy
import json
import os.path
import multiprocessing
from pathlib import Path
from typing import Optional, Dict, Any
from .jobs_history_journal import JobsHistory
from .db_connection_window import DatabaseConnectionWindow
from ...core.logger import get_module_logger
from ..base_window import BaseMainWindow
from PyQt6.QtWidgets import QDialog
from ..dialogs import SaveConfirmationDialog, SaveAsDialog

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
    from PyQt5.QtWidgets import QAction
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


class ConfigurerMainWindow(QDialog):
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int)
    config_changed = pyqtSignal(str)  # Сигнал изменения конфигурации
    window_closed = pyqtSignal()  # Сигнал закрытия окна

    def __init__(self, config_file_name, win_width, win_height, parent=None):
        # Инициализируем базовый класс
        super().__init__(parent)
        
        self.logger = get_module_logger("configurer_window")
        self.config_file_name = config_file_name
        self.setWindowTitle("EvilEye Configurer")
        self.resize(win_width, win_height)
        
        # Устанавливаем модальность
        self.setModal(True)
        
        # Добавляем атрибуты, которые использовались из BaseMainWindow
        self.has_unsaved_changes = False
        self.config_history_manager = None

        self.is_db_connected = False

        file_path = self.config_file_name  # 'configurer/initial_config.json'
        full_path = os.path.join(utils.get_project_root(), file_path)
        with open(full_path, 'r+') as params_file:
            config_params = json.load(params_file)
        
        # Больше не распаковываем секции пайплайна на корневой уровень

        with open(os.path.join(utils.get_project_root(), "database_config.json"), 'r+') as database_config_file:
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
            with open(os.path.join(utils.get_project_root(), "database_config.json")) as data_config_file:
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

        self._create_actions()
        self._connect_actions()
        self.run_flag = False
        
        # Создаем основной layout для QDialog
        main_layout = QVBoxLayout()
        
        # Добавляем меню-кнопки
        menu_layout = self._create_menu_bar()
        main_layout.addLayout(menu_layout)
        
        # Создаем scroll area для вкладок
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.tabs)
        self.scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        
        # Добавляем scroll area с вкладками
        main_layout.addWidget(self.scroll_area)
        
        # Устанавливаем layout для диалога
        self.setLayout(main_layout)
        
        # Устанавливаем минимальные размеры окна
        self.setMinimumSize(800, 600)
        self.resize(1200, 800)
        
        self._connect_to_db()

        self.result_filename = None
        multiprocessing.set_start_method('spawn')
        
        # Инициализация отслеживания изменений
        self._init_change_tracking()
        
        # Подключение сигналов для отслеживания изменений
        self._connect_change_tracking_signals()

    def _setup_tabs(self):
        self.tabs = QTabWidget()
        self.tabs.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
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
        # Для QDialog создаем меню как обычные кнопки в layout
        # Вместо menuBar создаем горизонтальный layout с кнопками
        menu_layout = QHBoxLayout()
        
        # Создаем кнопки вместо меню
        self.open_history_btn = QPushButton('Open History', self)
        self.load_from_history_btn = QPushButton('Load from History', self)
        self.save_btn = QPushButton('Save', self)
        self.save_as_btn = QPushButton('Save As', self)
        self.run_btn = QPushButton('Run', self)
        
        # Подключаем сигналы
        self.open_history_btn.clicked.connect(self._open_history)
        self.load_from_history_btn.clicked.connect(self._load_from_history)
        self.save_btn.clicked.connect(self._save_config)
        self.save_as_btn.clicked.connect(self._save_config_as)
        self.run_btn.clicked.connect(self._run_app)
        
        # Добавляем кнопки в layout
        menu_layout.addWidget(self.open_history_btn)
        menu_layout.addWidget(self.load_from_history_btn)
        menu_layout.addWidget(self.save_btn)
        menu_layout.addWidget(self.save_as_btn)
        menu_layout.addWidget(self.run_btn)
        menu_layout.addStretch()
        
        return menu_layout


    def _create_actions(self):  # Создание кнопок-действий
        self.save_params = QAction('&Save parameters', self)
        self.save_params.setIcon(QIcon(os.path.join(utils.get_project_root(), 'icons', 'save_icon.svg')))
        self.save_as_params = QAction('&Save As...', self)
        self.save_as_params.setIcon(QIcon(os.path.join(utils.get_project_root(), 'icons', 'save_icon.svg')))
        self.open_jobs_history = QAction('&Open history', self)
        self.load_from_history = QAction('&Load from History', self)
        self.start_app = QAction('&Run app', self)
        self.start_app.setIcon(QIcon(os.path.join(utils.get_project_root(), 'icons', 'run_app.svg')))
        icon_path = os.path.join(utils.get_project_root(), 'icons', 'journal.svg')
        self.open_jobs_history.setIcon(QIcon(icon_path))
        self.load_from_history.setIcon(QIcon(icon_path))

    def _connect_actions(self):
        self.save_params.triggered.connect(self._save_config)
        self.save_as_params.triggered.connect(self._save_config_as)
        self.open_jobs_history.triggered.connect(self._check_db_connection)
        self.load_from_history.triggered.connect(self._load_from_history)
        self.start_app.triggered.connect(self._prepare_running)

    @pyqtSlot()
    def _prepare_running(self):
        self.run_flag = True
        # Сохраняем конфигурацию перед запуском
        self._save_config()

    def _run_app(self):
        import subprocess
        import sys
        from pathlib import Path
        
        # Получаем путь к process.py
        project_root = Path(__file__).parent.parent.parent.parent
        process_script = project_root / "evileye" / "process.py"
        
        if process_script.exists():
            cmd = [sys.executable, str(process_script), "--config", self.result_filename, "--gui"]
            self.new_process = subprocess.Popen(cmd, cwd=project_root)
        else:
            self.logger.error(f"process.py not found at {process_script}")

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
                
                # Интегрируем с ConfigHistoryManager, если доступен
                if hasattr(self, 'db_controller') and self.db_controller:
                    try:
                        from ...database.config_history_manager import ConfigHistoryManager
                        config_history_manager = ConfigHistoryManager(self.db_controller)
                        self.jobs_history.set_config_history_manager(config_history_manager)
                        self.logger.info("ConfigHistoryManager integrated with JobsHistory")
                    except Exception as e:
                        self.logger.warning(f"Could not integrate ConfigHistoryManager: {e}")

            if self.jobs_history.isVisible():
                self.jobs_history.setVisible(False)
            else:
                self.jobs_history.setVisible(True)

        if self.src_hist_clicked:
            self.tabs.widget(0).open_src_list()

    @pyqtSlot()
    def _load_from_history(self):
        """Загрузить конфигурацию из истории"""
        try:
            # Проверяем доступность базы данных
            if not hasattr(self, 'db_controller') or not self.db_controller:
                QMessageBox.warning(
                    self,
                    "База данных недоступна",
                    "Для загрузки конфигурации из истории необходимо подключение к базе данных."
                )
                return
            
            # Создаем ConfigHistoryManager
            from ...database.config_history_manager import ConfigHistoryManager
            config_history_manager = ConfigHistoryManager(self.db_controller)
            
            # Получаем список уникальных конфигураций
            unique_configs = config_history_manager.get_unique_configurations(limit=20)
            
            if not unique_configs:
                QMessageBox.information(
                    self,
                    "История пуста",
                    "В истории конфигураций нет записей.\n"
                    "Запустите приложение хотя бы один раз для создания истории."
                )
                return
            
            # Создаем диалог выбора конфигурации
            from ...dialogs import ConfigRestoreDialog
            
            # Показываем диалог для выбора конфигурации
            # Используем первую конфигурацию как пример
            selected_config = unique_configs[0]
            
            # Создаем диалог восстановления
            dialog = ConfigRestoreDialog(selected_config, self)
            dialog.config_restored.connect(self._on_config_loaded_from_history)
            dialog.exec()
            
        except Exception as e:
            self.logger.error(f"Error loading from history: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось загрузить конфигурацию из истории:\n{str(e)}"
            )
    
    @pyqtSlot(dict)
    def _on_config_loaded_from_history(self, restore_data: dict):
        """Обработчик загрузки конфигурации из истории"""
        try:
            config_info = restore_data.get('config_info', {})
            configuration_data = config_info.get('configuration_info', {})
            
            if not configuration_data:
                QMessageBox.warning(
                    self,
                    "Ошибка",
                    "Не удалось получить данные конфигурации из истории."
                )
                return
            
            # Загружаем конфигурацию в текущие вкладки
            self._load_configuration_data(configuration_data)
            
            # Показываем уведомление об успешной загрузке
            QMessageBox.information(
                self,
                "Конфигурация загружена",
                f"Конфигурация из истории успешно загружена.\n"
                f"Job ID: {restore_data.get('job_id', 'N/A')}\n"
                f"Дата создания: {config_info.get('creation_time', 'N/A')}\n\n"
                f"Не забудьте сохранить изменения, если они нужны."
            )
            
            # Отмечаем, что есть несохраненные изменения
            self.has_unsaved_changes = True
            self._update_window_title()
            
        except Exception as e:
            self.logger.error(f"Error processing loaded config: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось обработать загруженную конфигурацию:\n{str(e)}"
            )
    
    def _load_configuration_data(self, config_data: dict):
        """Загрузить данные конфигурации в вкладки"""
        try:
            # Загружаем данные в соответствующие вкладки
            if 'sources' in config_data:
                self.tab_params['sources'].set_params(config_data['sources'])
            
            if 'detectors' in config_data:
                self.tab_params['detectors'].set_params(config_data['detectors'])
            
            if 'trackers' in config_data:
                self.tab_params['trackers'].set_params(config_data['trackers'])
            
            if 'handlers' in config_data:
                self.tab_params['handlers'].set_params(config_data['handlers'])
            
            if 'visualizers' in config_data:
                self.tab_params['visualizers'].set_params(config_data['visualizers'])
            
            if 'events' in config_data:
                self.tab_params['events'].set_params(config_data['events'])
            
            if 'events_detectors' in config_data:
                self.tab_params['events_detectors'].set_params(config_data['events_detectors'])
            
            self.logger.info("Configuration data loaded into tabs")
            
        except Exception as e:
            self.logger.error(f"Error loading configuration data: {e}")
            raise

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
        # Секции, которые относятся к пайплайну
        pipeline_sections = {
            'sources', 'preprocessors', 'detectors', 'trackers', 'mc_trackers',
            'attributes_roi', 'attributes_classifier'
        }

        # Обеспечим наличие секции pipeline
        if 'pipeline' not in self.config_result or not isinstance(self.config_result['pipeline'], dict):
            self.config_result['pipeline'] = {}

        # Сначала очистим возможные дубли секций пайплайна на корневом уровне
        for key in list(self.config_result.keys()):
            if key in pipeline_sections:
                try:
                    del self.config_result[key]
                except Exception:
                    pass

        # Запишем актуальные параметры в нужные разделы
        for section_config in configs:
            section_name = section_config[0]
            section_params = section_config[1]
            if section_name in pipeline_sections:
                self.config_result['pipeline'][section_name] = section_params
            else:
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
        # Проверяем, есть ли несохраненные изменения
        if self.has_unsaved_changes:
            reply = QMessageBox.question(
                self, 
                'Несохраненные изменения',
                'У вас есть несохраненные изменения. Хотите сохранить их перед закрытием?',
                QMessageBox.StandardButton.Save | 
                QMessageBox.StandardButton.Discard | 
                QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save
            )
            
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            elif reply == QMessageBox.StandardButton.Save:
                # Сохраняем конфигурацию
                self._save_config()
        
        # Закрываем вкладки
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        
        # Очищаем подключение к базе данных
        self.logger.info('DB jobs_conn removed')
        QSqlDatabase.removeDatabase('jobs_conn')
        
        # Испускаем сигнал закрытия окна
        self.window_closed.emit()
        
        # НЕ закрываем все окна приложения!
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
    
    # === Новые методы для отслеживания изменений и улучшенного сохранения ===
    
    def _init_change_tracking(self) -> None:
        """Инициализация отслеживания изменений"""
        self._original_config = copy.deepcopy(self.config_result)
        self._has_unsaved_changes = False
        
        # Сохраняем оригинальные значения для сравнения
        self._original_tab_data = {}
        for tab_name, tab_widget in self.tab_params.items():
            if hasattr(tab_widget, 'get_params'):
                self._original_tab_data[tab_name] = tab_widget.get_params()
    
    def _connect_change_tracking_signals(self) -> None:
        """Подключение сигналов для отслеживания изменений"""
        # Подключаем сигналы изменения вкладок
        for tab_name, tab_widget in self.tab_params.items():
            if hasattr(tab_widget, 'params_changed'):
                tab_widget.params_changed.connect(self._on_tab_params_changed)
            elif hasattr(tab_widget, 'valueChanged'):
                # Для виджетов с сигналом valueChanged
                tab_widget.valueChanged.connect(self._on_tab_params_changed)
            elif hasattr(tab_widget, 'textChanged'):
                # Для текстовых полей
                tab_widget.textChanged.connect(self._on_tab_params_changed)
    
    @pyqtSlot()
    def _on_tab_params_changed(self) -> None:
        """Обработчик изменения параметров вкладки"""
        self._check_for_changes()
    
    def _check_for_changes(self) -> None:
        """Проверка наличия изменений в конфигурации"""
        try:
            # Получаем текущие параметры
            current_config = self._get_current_config()
            
            # Сравниваем с оригинальной конфигурацией
            has_changes = current_config != self._original_config
            
            if has_changes != self._has_unsaved_changes:
                self._has_unsaved_changes = has_changes
                self.has_unsaved_changes = has_changes
                
                if has_changes:
                    self.logger.debug("Configuration changes detected")
                else:
                    self.logger.debug("Configuration changes resolved")
                    
        except Exception as e:
            self.logger.error(f"Error checking for changes: {e}")
    
    def _get_current_config(self) -> Dict[str, Any]:
        """Получить текущую конфигурацию из всех вкладок"""
        try:
            self._process_params_strings()
            return copy.deepcopy(self.config_result)
        except Exception as e:
            self.logger.error(f"Error getting current config: {e}")
            return {}
    
    @pyqtSlot()
    def _save_config(self) -> None:
        """Сохранить конфигурацию в текущий файл"""
        if not self.config_file_name:
            # Если нет текущего файла, показываем диалог "Сохранить как"
            self._save_config_as()
            return
        
        try:
            # Получаем текущую конфигурацию
            current_config = self._get_current_config()
            
            # Валидируем конфигурацию
            if not self._validate_config(current_config):
                return
            
            # Путь сохранения
            full_path = os.path.join(utils.get_project_root(), self.config_file_name)

            # Централизованное сохранение через контроллер, если доступен
            controller = getattr(getattr(self, 'parent', None), 'controller', None)
            if controller and hasattr(controller, 'save_config'):
                try:
                    # Передаём путь в контроллер
                    controller.params_path = full_path
                    # Обновляем текущие параметры контроллера перед сохранением
                    controller.params = copy.deepcopy(current_config)
                    ok = controller.save_config(full_path)
                    if not ok:
                        raise RuntimeError("controller.save_config() returned False")
                except Exception as e:
                    # Fallback: локальная запись, если контроллер не сохранил
                    with open(full_path, 'w', encoding='utf-8') as file:
                        json.dump(current_config, file, indent=4, ensure_ascii=False)
            else:
                # Fallback: локальная запись, если контроллер недоступен
                with open(full_path, 'w', encoding='utf-8') as file:
                    json.dump(current_config, file, indent=4, ensure_ascii=False)
            
            # Обновляем оригинальную конфигурацию
            self._original_config = copy.deepcopy(current_config)
            self._has_unsaved_changes = False
            self.has_unsaved_changes = False
            
            # Показываем уведомление об успешном сохранении
            QMessageBox.information(
                self, 
                "Сохранение", 
                f"Конфигурация успешно сохранена в:\n{full_path}"
            )
            
            # Испускаем сигнал об изменении конфигурации
            self.config_changed.emit(self.config_file_name)
            
            self.logger.info(f"Configuration saved to: {full_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving configuration: {e}")
            QMessageBox.critical(
                self, 
                "Ошибка сохранения", 
                f"Не удалось сохранить конфигурацию:\n{str(e)}"
            )
    
    @pyqtSlot()
    def _save_config_as(self) -> None:
        """Сохранить конфигурацию под новым именем"""
        try:
            # Показываем диалог выбора файла
            file_path = SaveAsDialog.show_dialog(self.config_file_name, self)
            
            if not file_path:
                return  # Пользователь отменил
            
            # Получаем текущую конфигурацию
            current_config = self._get_current_config()
            
            # Валидируем конфигурацию
            if not self._validate_config(current_config):
                return
            
            # Централизованное сохранение через контроллер, если доступен
            controller = getattr(getattr(self, 'parent', None), 'controller', None)
            if controller and hasattr(controller, 'save_config'):
                try:
                    controller.params_path = file_path
                    controller.params = copy.deepcopy(current_config)
                    ok = controller.save_config(file_path)
                    if not ok:
                        raise RuntimeError("controller.save_config() returned False")
                except Exception:
                    # Fallback: локальная запись
                    with open(file_path, 'w', encoding='utf-8') as file:
                        json.dump(current_config, file, indent=4, ensure_ascii=False)
            else:
                # Fallback: локальная запись
                with open(file_path, 'w', encoding='utf-8') as file:
                    json.dump(current_config, file, indent=4, ensure_ascii=False)
            
            # Обновляем текущий файл конфигурации
            self.config_file_name = file_path
            self.config_file = file_path
            
            # Обновляем оригинальную конфигурацию
            self._original_config = copy.deepcopy(current_config)
            self._has_unsaved_changes = False
            self.has_unsaved_changes = False
            
            # Обновляем заголовок окна
            self.setWindowTitle(f"EvilEye Configurer - {Path(file_path).name}")
            
            # Показываем уведомление об успешном сохранении
            QMessageBox.information(
                self, 
                "Сохранение", 
                f"Конфигурация успешно сохранена в:\n{file_path}"
            )
            
            # Испускаем сигнал об изменении конфигурации
            self.config_changed.emit(self.config_file_name)
            
            self.logger.info(f"Configuration saved as: {file_path}")
            
        except Exception as e:
            self.logger.error(f"Error saving configuration as: {e}")
            QMessageBox.critical(
                self, 
                "Ошибка сохранения", 
                f"Не удалось сохранить конфигурацию:\n{str(e)}"
            )
    
    def _validate_config(self, config: Dict[str, Any]) -> bool:
        """Валидация конфигурации перед сохранением"""
        try:
            # Проверяем обязательные секции
            required_sections = ['sources', 'detectors', 'trackers', 'visualizer']
            for section in required_sections:
                if section not in config:
                    QMessageBox.warning(
                        self, 
                        "Ошибка валидации", 
                        f"Отсутствует обязательная секция: {section}"
                    )
                    return False
            
            # Проверяем источники
            sources = config.get('sources', [])
            if not sources:
                QMessageBox.warning(
                    self, 
                    "Ошибка валидации", 
                    "Необходимо настроить хотя бы один источник"
                )
                return False
            
            # Дополнительные проверки можно добавить здесь
            
            return True
            
        except Exception as e:
            self.logger.error(f"Error validating config: {e}")
            QMessageBox.critical(
                self, 
                "Ошибка валидации", 
                f"Ошибка при валидации конфигурации:\n{str(e)}"
            )
            return False
    
    # === Реализация абстрактных методов BaseMainWindow ===
    
    def get_config_data(self) -> Optional[Dict[str, Any]]:
        """Получить данные конфигурации для сохранения"""
        try:
            return self._get_current_config()
        except Exception as e:
            self.logger.error(f"Error getting config data: {e}")
            return None
    
    def apply_config_data(self, config_data: Dict[str, Any]) -> bool:
        """Применить данные конфигурации"""
        try:
            # Обновляем параметры
            self.params = copy.deepcopy(config_data)
            self.config_result = copy.deepcopy(config_data)
            
            # Обновляем вкладки
            for tab_name, tab_widget in self.tab_params.items():
                if hasattr(tab_widget, 'set_params'):
                    section_data = config_data.get(tab_name, {})
                    tab_widget.set_params(section_data)
            
            # Обновляем оригинальную конфигурацию
            self._original_config = copy.deepcopy(config_data)
            self._has_unsaved_changes = False
            self.has_unsaved_changes = False
            
            self.logger.info("Configuration data applied successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Error applying config data: {e}")
            return False
    
    def on_config_changed(self, config_file: str) -> None:
        """Обработчик изменения конфигурации"""
        if config_file == self.config_file_name:
            self.logger.info(f"Configuration file changed: {config_file}")
            # Можно добавить логику для перезагрузки конфигурации
