import json
import os

try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QSizePolicy, QMenuBar, QToolBar,
        QMenu, QMainWindow, QApplication, QMessageBox
    )

    from PyQt6.QtCore import QTimer
    from PyQt6.QtGui import QPixmap, QIcon, QCursor
    from PyQt6.QtGui import QAction
    from PyQt6.QtCore import Qt
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5 import QtGui
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QSizePolicy, QMenuBar, QToolBar,
        QMenu, QMainWindow, QApplication, QMessageBox
    )

    from PyQt5.QtCore import QTimer
    from PyQt5.QtGui import QPixmap, QIcon, QCursor
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import Qt
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5

from ..core.logger import get_module_logger

import sys
import cv2
import os
from pathlib import Path
from ..utils import utils
from ..utils import utils as utils_utils
from .video_thread import VideoThread
from .db_journal import DatabaseJournalWindow
from .events_journal_json import EventsJournalJson
from .zone_window import ZoneWindow
from .configurer.configurer_tabs.src_widget import SourceWidget
from .configurer.configurer_window import ConfigurerMainWindow
from .configurer.jobs_history_journal import JobsHistory
from .window_manager import get_window_manager
from ..database.config_history_manager import ConfigHistoryManager
from .roi_editor_window import ROIEditorWindow
from .dialogs.class_mapping_dialog import ClassMappingDialog
sys.path.append(str(Path(__file__).parent.parent.parent))


# Собственный класс для label, чтобы переопределить двойной клик мышкой
class DoubleClickLabel(QLabel):
    double_click_signal = pyqtSignal()
    add_zone_signal = pyqtSignal()
    add_roi_signal = pyqtSignal()
    regular_click_signal = pyqtSignal()
    is_add_zone_clicked = False
    is_add_roi_clicked = False

    def __init__(self):
        super(DoubleClickLabel, self).__init__()
        self.is_full = False
        self.is_ready_to_display = False

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_click_signal.emit()

    def mousePressEvent(self, event):
        if DoubleClickLabel.is_add_zone_clicked:
            self.add_zone_signal.emit()
        elif DoubleClickLabel.is_add_roi_clicked:
            self.add_roi_signal.emit()
        else:
            # Обычный клик - обновляем последний активный источник
            self.regular_click_signal.emit()
        event.accept()

    def add_zone_clicked(self, flag):  # Для изменения курсора в момент выбора источника
        DoubleClickLabel.is_add_zone_clicked = flag
        if flag:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))
    
    def add_roi_clicked(self, flag):  # Для изменения курсора в момент выбора источника для ROI
        DoubleClickLabel.is_add_roi_clicked = flag
        if flag:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def ready_to_display(self, flag):
        self.is_ready_to_display = flag


class MainWindow(QMainWindow):
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int)
    add_roi_signal = pyqtSignal(int)
    # UI-level signalization controls
    set_signal_params_signal = pyqtSignal(bool, tuple)

    def __init__(self, controller, params_file_path, params, win_width, win_height):
        super().__init__()
        self.logger = get_module_logger("main_window")
        self.setWindowTitle("EvilEye")
        self.resize(win_width, win_height)
        self.slots = {'update_image': self.update_image, 'update_original_cv_image': self.update_original_cv_image, 'clean_image_available': self.clean_image_available, 'open_zone_win': self.open_zone_win, 'open_roi_win': self.open_roi_win}
        self.signals = {'display_zones_signal': self.display_zones_signal, 'add_zone_signal': self.add_zone_signal, 'add_roi_signal': self.add_roi_signal}

        self.controller = controller

        self.params_path = params_file_path
        self.params = params
        
        # Инициализация WindowManager
        self.window_manager = get_window_manager()
        self.settings_window = None
        self.config_history_window = None
        self.config_history_manager = None

        self.rows = self.params['visualizer'].get('num_height', 1)
        self.cols = self.params['visualizer'].get('num_width', 1)
        self.cameras = self.params.get('pipeline', {}).get('sources', list())

        self.num_cameras = len(self.cameras)
        self.src_ids = []
        for camera in self.cameras:
            for src_id in camera['source_ids']:
                self.src_ids.append(src_id)
        self.num_sources = len(self.src_ids)

        self.labels_sources_ids = {}  # Для сопоставления id источника с id label
        self.labels = []
        self.threads = []
        self.hlayouts = []
        
        # Отслеживание активных источников для редакторов
        self.last_active_source_id = None
        self.current_roi_source_id = None
        self.current_zone_source_id = None
        self.last_pixmaps = {}  # {source_id: QPixmap} - последние кадры для каждого источника
        self.last_clean_cv_images = {}  # {source_id: cv_image} - чистые OpenCV изображения для каждого источника

        self.setCentralWidget(QWidget())
        self._create_actions()
        self._connect_actions()

        close_app = False
        if self.controller.enable_close_from_gui and not self.controller.show_main_gui and self.controller.show_journal:
            close_app = True

        # Create journal window (DB or JSON mode)
        if hasattr(self.controller, 'use_database') and self.controller.use_database:
            try:
                self.db_journal_win = DatabaseJournalWindow(self, self.params, self.controller.database_config, close_app,
                                                           logger_name="db_journal", parent_logger=self.logger)
                self.db_journal_win.setVisible(False)
            except Exception as e:
                self.logger.warning(f"Warning: Failed to create database journal window. Switching to JSON mode. Reason: {e}")
                # Fallback to JSON journal mode
                self._create_json_journal_window()
        else:
            # Get image_dir from database_config (even if database is disabled)
            images_dir = 'EvilEyeData'  # default
            if hasattr(self.controller, 'database_config') and self.controller.database_config.get('database', {}):
                images_dir = self.controller.database_config['database'].get('images_dir', images_dir)
            
            # Check if directory exists before creating journal
            if os.path.exists(images_dir):
                try:
                    from . import json_journal
                    self.db_journal_win = json_journal.JsonJournalWindow(self, self.params, images_dir, close_app,
                                                                        logger_name="json_journal", parent_logger=self.logger)
                    self.db_journal_win.setVisible(False)
                except Exception as e:
                    self.logger.error(f"JSON journal creation error: {e}")
                    self.db_journal_win = None
            else:
                self.logger.warning(f"Images folder does not exist: {images_dir}")
                self.db_journal_win = None
        self.zone_window = ZoneWindow(self.params)
        self.zone_window.zones_updated.connect(self._on_zones_updated)
        self.zone_window.zone_editor_closed.connect(self._on_zone_editor_closed)
        self.zone_window.setVisible(False)

        # ROI Editor window (new non-modal window)
        try:
            self.roi_editor_window = ROIEditorWindow(self.params)
            # Не сохраняем конфигурацию при каждом обновлении ROI — работаем только по закрытию
            self.roi_editor_window.roi_updated.connect(lambda rois: None)
            # Обновление ROI детектора по закрытию ROI окна
            self.roi_editor_window.roi_editor_closed.connect(self._on_roi_editor_closed)
            self.roi_editor_window.setVisible(False)
        except Exception as e:
            self.logger.error(f"Failed to create ROIEditorWindow: {e}")
            self.roi_editor_window = None

        vertical_layout = QVBoxLayout()
        for i in range(self.rows):
            self.hlayouts.append(QHBoxLayout())
            vertical_layout.addLayout(self.hlayouts[-1])
        self.centralWidget().setLayout(vertical_layout)
        self.setup_layout()

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_controller_status)
        self.timer.setInterval(1000)
        self.timer.start()

        # Configure journal button after journal window is created
        self._configure_journal_button()
        
        # Create menu and toolbar after journal window is created
        self.menu_height = 0
        self._create_menu_bar()

        self.toolbar_width = 0
        self._create_toolbar()

        # Connect signalization params to visualizer
        self.set_signal_params_signal.connect(self._broadcast_signal_params)

        # Schedule zones emission after startup if persistent flag is enabled
        try:
            from PyQt6.QtCore import QTimer as _QTimer6
            _Timer = _QTimer6
        except Exception:
            from PyQt5.QtCore import QTimer as _QTimer5
            _Timer = _QTimer5
        try:
            _Timer.singleShot(300, self._emit_zones_from_config_if_enabled)
            _Timer.singleShot(1500, self._emit_zones_from_config_if_enabled)
        except Exception:
            pass

    def setup_layout(self):
        self.centralWidget().layout().setContentsMargins(0, 0, 0, 0)
        grid_cols = 0
        grid_rows = 0
        for i in range(self.num_sources):
            self.labels.append(DoubleClickLabel())
            self.labels_sources_ids[i] = self.src_ids[i]
            # Изменяем размер изображения по двойному клику
            self.labels[-1].double_click_signal.connect(self.change_screen_size)
            self.labels[-1].setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            self.labels[-1].add_zone_signal.connect(self.emit_add_zone_signal)
            self.labels[-1].add_roi_signal.connect(self.emit_add_roi_signal)
            self.labels[-1].regular_click_signal.connect(self.emit_regular_click_signal)

            # Добавляем виджеты в layout в зависимости от начальных параметров (кол-во изображений по ширине и высоте)
            if grid_cols > self.cols - 1:
                grid_cols = 0
                grid_rows += 1
                # Гарантируем существование нужной строки лэйаута
                if grid_rows >= len(self.hlayouts):
                    new_h = QHBoxLayout()
                    self.hlayouts.append(new_h)
                    # Добавляем новый горизонтальный лэйаут в основной вертикальный
                    self.centralWidget().layout().addLayout(new_h)
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignmentFlag.AlignCenter)
                grid_cols += 1
            else:
                # Гарантируем существование нужной строки лэйаута
                if grid_rows >= len(self.hlayouts):
                    new_h = QHBoxLayout()
                    self.hlayouts.append(new_h)
                    self.centralWidget().layout().addLayout(new_h)
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignmentFlag.AlignCenter)
                grid_cols += 1
            # Threads are managed by Visualizer; no direct thread creation here

    def _create_menu_bar(self):
        menu = self.menuBar()

        view_menu = QMenu('&View', self)
        menu.addMenu(view_menu)
        view_menu.addAction(self.objects_journal)
        view_menu.addAction(self.events_journal)
        view_menu.addAction(self.toggle_signal)
        self.menu_height = view_menu.frameGeometry().height()

        edit_menu = QMenu('&Edit', self)
        menu.addMenu(edit_menu)
        edit_menu.addSeparator()
        edit_menu.addAction(self.open_zone_editor)
        edit_menu.addAction(self.open_roi_editor)
        edit_menu.addAction(self.open_class_mapping_editor)
        
        settings_menu = QMenu('&Settings', self)
        menu.addMenu(settings_menu)
        settings_menu.addAction(self.open_settings)
        settings_menu.addAction(self.open_config_history)
        
        # Tools menu
        #tools_menu = QMenu('&Tools', self)
        #menu.addMenu(tools_menu)
        #tools_menu.addAction(self.validate_config)
        #tools_menu.addSeparator()
        #tools_menu.addAction(self.export_config)
        #tools_menu.addAction(self.import_config)

        #configure_menu = QMenu('&Configure', self)
        #menu.addMenu(configure_menu)
        #configure_menu.addAction(self.add_channel)
        #configure_menu.addAction(self.del_channel)

    def _create_toolbar(self):
        view_toolbar = QToolBar('View', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, view_toolbar)
        view_toolbar.addAction(self.objects_journal)
        view_toolbar.addAction(self.events_journal)
        self.toolbar_width = view_toolbar.frameGeometry().width()

        edit_toolbar = QToolBar('Edit', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, edit_toolbar)
        edit_toolbar.addAction(self.add_zone)
        # Add ROI editor action to right toolbar
        edit_toolbar.addAction(self.open_roi_editor)
        edit_toolbar.addAction(self.open_settings)
        edit_toolbar.addAction(self.open_config_history)
        edit_toolbar.addAction(self.toggle_zones)
        self.toolbar_width = edit_toolbar.frameGeometry().width()

    def _create_actions(self):  # Создание кнопок-действий
        # Journal actions (Objects / Events)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'journal.svg')
        self.objects_journal = QAction('&Objects Journal', self)
        self.objects_journal.setIcon(QIcon(icon_path))
        self.events_journal = QAction('&Events Journal', self)
        self.events_journal.setIcon(QIcon(icon_path))

        self.add_zone = QAction('&Add zone', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'add_zone.svg')
        self.add_zone.setIcon(QIcon(icon_path))
        # Persistent display zones toggle (visualizer param)
        self.toggle_zones = QAction('&Display zones', self)
        self.toggle_zones.setCheckable(True)
        self.toggle_zones.setChecked(self.params['visualizer'].get('display_zones', False))
        # Add toggle for event signalization
        self.toggle_signal = QAction('&Event Signalization', self)
        self.toggle_signal.setCheckable(True)
        self.toggle_signal.setChecked(self.params['visualizer'].get('event_signal_enabled', False))

        self.add_channel = QAction('&Add Channel', self)
        self.del_channel = QAction('&Del Channel', self)
        
        # Settings action
        self.open_settings = QAction('&Settings', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'save_icon.svg')
        self.open_settings.setIcon(QIcon(icon_path))
        
        # Configuration History action
        self.open_config_history = QAction('&Configuration History', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'journal.svg')
        self.open_config_history.setIcon(QIcon(icon_path))
        
        # Visual Editors actions
        self.open_roi_editor = QAction('&ROI Editor', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'roi_editor.svg')
        self.open_roi_editor.setIcon(QIcon(icon_path))
        self.open_roi_editor.setToolTip("Open ROI Editor for defining regions of interest")
        try:
            icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'roi_draw.svg')
            if os.path.exists(icon_path):
                self.open_roi_editor.setIcon(QIcon(icon_path))
        except Exception:
            pass
        
        self.open_zone_editor = QAction('&Zone Editor', self)
        self.open_zone_editor.setToolTip("Open Zone Editor for defining event zones")
        
        self.open_class_mapping_editor = QAction('&Class Mapping Editor', self)
        self.open_class_mapping_editor.setToolTip("Open Class Mapping Editor for managing object classes")
        
        # Tools menu actions
        self.validate_config = QAction('&Validate Configuration', self)
        self.validate_config.setToolTip("Validate current configuration")
        
        self.export_config = QAction('&Export Configuration', self)
        self.export_config.setToolTip("Export current configuration to file")
        
        self.import_config = QAction('&Import Configuration', self)
        self.import_config.setToolTip("Import configuration from file")

    def _connect_actions(self):
        self.objects_journal.triggered.connect(self.open_objects_journal)
        self.events_journal.triggered.connect(self.open_events_journal)
        self.add_zone.triggered.connect(self.open_zone_editor_window)
        self.toggle_signal.toggled.connect(self._toggle_signalization)
        self.toggle_zones.toggled.connect(self._toggle_display_zones)
        self.add_channel.triggered.connect(self.add_channel_slot)
        self.del_channel.triggered.connect(self.del_channel_slot)
        self.open_settings.triggered.connect(self.open_settings_window)
        self.open_config_history.triggered.connect(self.open_config_history_window)
        
        # Visual Editors connections
        self.open_roi_editor.triggered.connect(self.open_roi_editor_window)
        self.open_zone_editor.triggered.connect(self.open_zone_editor_window)
        self.open_class_mapping_editor.triggered.connect(self.open_class_mapping_editor_window)
        
        # Tools connections
        self.validate_config.triggered.connect(self.validate_current_config)
        self.export_config.triggered.connect(self.export_current_config)
        self.import_config.triggered.connect(self.import_config_from_file)

    def _configure_journal_button(self):
        """Configure journal actions based on database mode and availability"""
        available = self.db_journal_win is not None
        self.objects_journal.setEnabled(available)
        self.events_journal.setEnabled(available)
        self.objects_journal.setToolTip("Open Objects journal" if available else "Journal is not available")
        self.events_journal.setToolTip("Open Events journal" if available else "Journal is not available")
        
        # Configuration History доступна только с DatabaseJournalWindow
        config_history_available = (available and 
                                  hasattr(self.db_journal_win, 'db_controller') and 
                                  self.db_journal_win.db_controller is not None)
        self.open_config_history.setEnabled(config_history_available)
        self.open_config_history.setToolTip(
            "Open Configuration History" if config_history_available 
            else "Configuration History requires database mode"
        )

    def _emit_zones_from_config_if_enabled(self):
        try:
            if self.params.get('visualizer', {}).get('display_zones', False):
                zones = {}
                if hasattr(self, 'zone_window') and self.zone_window:
                    try:
                        zones = self.zone_window.get_zone_info()
                    except Exception:
                        zones = {}
                self.display_zones_signal.emit(zones)
        except Exception:
            pass

    @pyqtSlot()
    def select_source(self):  # Выбор источника для добавления зон
        for label in self.labels:
            label.add_zone_clicked(True)

    @pyqtSlot()
    def _ensure_journal_window(self):
        if self.db_journal_win is None:
            self.logger.warning("Journal unavailable (database disabled or initialization failed)")
            return False
        return True

    @pyqtSlot()
    def open_objects_journal(self):
        if not self._ensure_journal_window():
            return
        # Ensure window is shown and focused on each click
        self.db_journal_win.show()
        try:
            self.db_journal_win.raise_()
            self.db_journal_win.activateWindow()
        except Exception:
            pass
        try:
            # Ensure default tabs restored if user closed them
            if hasattr(self.db_journal_win, '_ensure_default_tabs'):
                self.db_journal_win._ensure_default_tabs()
            # JSON journal has ensure_tab; DB journal does not
            if hasattr(self.db_journal_win, 'ensure_tab'):
                idx = self.db_journal_win.ensure_tab('Objects')
                if idx >= 0:
                    self.db_journal_win.tabs.setCurrentIndex(idx)
            elif hasattr(self.db_journal_win, 'tabs'):
                tabs = self.db_journal_win.tabs
                for i in range(tabs.count()):
                    if tabs.tabText(i).lower().startswith('objects'):
                        tabs.setCurrentIndex(i)
                        tabs.widget(i).setVisible(True)
                        tabs.tabBar().setTabVisible(i, True)
                        break
        except Exception:
            pass

    @pyqtSlot()
    def open_events_journal(self):
        if not self._ensure_journal_window():
            return
        self.db_journal_win.show()
        try:
            self.db_journal_win.raise_()
            self.db_journal_win.activateWindow()
        except Exception:
            pass
        try:
            if hasattr(self.db_journal_win, '_ensure_default_tabs'):
                self.db_journal_win._ensure_default_tabs()
            if hasattr(self.db_journal_win, 'ensure_tab'):
                idx = self.db_journal_win.ensure_tab('Events')
                if idx >= 0:
                    self.db_journal_win.tabs.setCurrentIndex(idx)
            elif hasattr(self.db_journal_win, 'tabs'):
                tabs = self.db_journal_win.tabs
                for i in range(tabs.count()):
                    if tabs.tabText(i).lower().startswith('events'):
                        tabs.setCurrentIndex(i)
                        tabs.widget(i).setVisible(True)
                        tabs.tabBar().setTabVisible(i, True)
                        break
        except Exception:
            pass

    @pyqtSlot(int, QPixmap)
    def open_zone_win(self, label_id: int, pixmap: QPixmap):
        if self.zone_window.isVisible():
            self.zone_window.setVisible(False)
        else:
            self.zone_window.setVisible(True)
            # Получаем source_id для данного label_id
            source_id = self.labels_sources_ids.get(label_id, 0)
            self.current_zone_source_id = source_id
            
            # Получаем чистое OpenCV изображение для этого источника
            clean_cv_image = self.last_clean_cv_images.get(source_id)
            
            # Если нет в кэше, пытаемся получить из VideoThread
            if clean_cv_image is None:
                clean_cv_image = self._get_clean_image_from_thread(source_id)
            
            # Проверяем наличие чистого OpenCV изображения
            if clean_cv_image is None:
                self.logger.error(f"No clean OpenCV image available for source {source_id} from signal")
                return
            
            self.logger.info(f"Using clean OpenCV image for source {source_id} from signal")
            self.zone_window.set_cv_image(source_id, clean_cv_image)
            
            # Загружаем зоны из конфигурации
            zones_data = self.zone_window.get_zones_for_source(source_id)
            if zones_data:
                self.logger.info(f"Loaded {len(zones_data)} zones for source {source_id}")
        for label in self.labels:
            label.add_zone_clicked(False)
    
    @pyqtSlot(int, QPixmap)
    def open_roi_win(self, label_id: int, pixmap: QPixmap):
        """Открыть ROI Editor с изображением из активного источника"""
        try:
            dialog = ROIEditorDialog(self)
            dialog.roi_updated.connect(self._on_roi_updated)
            
            # Получаем source_id для данного label_id
            source_id = self.labels_sources_ids.get(label_id, 0)
            self.current_roi_source_id = source_id
            
            # Устанавливаем изображение из активного источника
            dialog.set_image_from_pixmap(pixmap)
            
            # Загружаем ROI из конфигурации
            self.logger.info(f"Passing params to ROI editor: {type(self.params)}")
            self.logger.info(f"Params keys: {list(self.params.keys()) if isinstance(self.params, dict) else 'Not a dict'}")
            
            # Логируем всю информацию о детекторах
            self.logger.info("=== STARTING DETECTOR CHECK ===")
            self._log_all_detector_info()
            self.logger.info("=== FINISHED DETECTOR CHECK ===")
            
            # Попробуем получить детекторы из pipeline
            self.logger.info("Attempting to get detectors from pipeline...")
            pipeline_params = self._get_detectors_from_pipeline()
            self.logger.info(f"Pipeline params result: {pipeline_params is not None}")
            if pipeline_params:
                self.logger.info(f"Got detectors from pipeline: {len(pipeline_params.get('detectors', []))}")
                dialog.set_rois_from_config(pipeline_params, source_id)
            elif isinstance(self.params, dict) and 'detectors' in self.params:
                self.logger.info(f"Detectors count: {len(self.params['detectors'])}")
                dialog.set_rois_from_config(self.params, source_id)
            else:
                # Попробуем загрузить конфигурацию из файла
                self.logger.info("No detectors in params, trying to load from file")
                try:
                    import json
                    with open(self.params_path, 'r', encoding='utf-8') as f:
                        file_params = json.load(f)
                    self.logger.info(f"Loaded from file: {list(file_params.keys())}")
                    if 'detectors' in file_params:
                        self.logger.info(f"File detectors count: {len(file_params['detectors'])}")
                        dialog.set_rois_from_config(file_params, source_id)
                    else:
                        dialog.set_rois_from_config(self.params, source_id)
                except Exception as e:
                    self.logger.error(f"Error loading config from file: {e}")
                    dialog.set_rois_from_config(self.params, source_id)
            
            dialog.exec()
        except Exception as e:
            self.logger.error(f"Error opening ROI Editor with source image: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть ROI Editor:\n{str(e)}"
            )

    @pyqtSlot(int, QPixmap)
    def update_image(self, label_id: int, picture: QPixmap):
        # Обновляет label, в котором находится изображение
        if 0 <= label_id < len(self.labels):
            self.labels[label_id].setPixmap(picture)
            # Сохраняем последний pixmap для источника
            source_id = self.labels_sources_ids.get(label_id)
            if source_id is not None:
                self.last_pixmaps[source_id] = picture.copy()
    
    @pyqtSlot(int, object)
    def update_original_cv_image(self, label_id: int, original_cv_image):
        # Сохраняем оригинальное OpenCV изображение в last_clean_cv_images (они содержат одинаковые данные)
        source_id = self.labels_sources_ids.get(label_id)
        if source_id is not None:
            # Создаем копию OpenCV изображения
            import copy
            self.last_clean_cv_images[source_id] = copy.deepcopy(original_cv_image)
            h, w = original_cv_image.shape[:2]
            self.logger.debug(f"Saved original CV image for source {source_id}: {w}x{h}")

    @pyqtSlot(int, object)
    def clean_image_available(self, label_id: int, clean_cv_image):
        """Обновление чистого OpenCV изображения без нарисованных элементов для ROI Editor"""
        try:
            # Сохраняем чистое изображение для ROI Editor
            source_id = self.labels_sources_ids.get(label_id)
            if source_id is not None:
                # Создаем копию чистого OpenCV изображения
                import copy
                self.last_clean_cv_images[source_id] = copy.deepcopy(clean_cv_image)
                h, w = clean_cv_image.shape[:2]
                self.logger.debug(f"Saved clean CV image for source {source_id}: {w}x{h}")
        except Exception as e:
            self.logger.error(f"Error updating clean CV image: {e}")

    @pyqtSlot(bool)
    def _toggle_signalization(self, enabled: bool):
        color = tuple(self.params['visualizer'].get('event_signal_color', [255, 0, 0]))
        self._broadcast_signal_params(enabled, color)

    @pyqtSlot(bool, tuple)
    def _broadcast_signal_params(self, enabled: bool, color: tuple):
        for t in self.threads:
            try:
                t.set_signal_params(enabled, color)
            except Exception:
                pass

    # Event state routed directly by Controller → Visualizer now

    @pyqtSlot()
    def change_screen_size(self):
        sender = self.sender()
        if sender.is_full:
            sender.is_full = False
            VideoThread.rows = self.rows
            VideoThread.cols = self.cols
            for label in self.labels:
                if sender != label:
                    label.show()
        else:
            sender.is_full = True
            for label in self.labels:
                if sender != label:
                    label.hide()
            VideoThread.rows = 1
            VideoThread.cols = 1
        self.controller.set_current_main_widget_size(self.geometry().width() - self.toolbar_width,
                                                     self.geometry().height() - self.menu_height)

    @pyqtSlot()
    def emit_add_zone_signal(self):
        label = self.sender()
        label_id = self.labels.index(label)
        # Обновляем последний активный источник
        if label_id in self.labels_sources_ids:
            self.last_active_source_id = self.labels_sources_ids[label_id]
        self.add_zone_signal.emit(label_id)
    
    @pyqtSlot()
    def emit_add_roi_signal(self):
        label = self.sender()
        label_id = self.labels.index(label)
        # Обновляем последний активный источник
        if label_id in self.labels_sources_ids:
            self.last_active_source_id = self.labels_sources_ids[label_id]
        self.add_roi_signal.emit(label_id)

    @pyqtSlot()
    def emit_regular_click_signal(self):
        """Обработка обычного клика на источник"""
        label = self.sender()
        label_id = self.labels.index(label)
        # Обновляем последний активный источник
        if label_id in self.labels_sources_ids:
            self.last_active_source_id = self.labels_sources_ids[label_id]
            self.highlight_selected_source(label_id)
            self.logger.info(f"Updated last active source to: {self.last_active_source_id}")

    def highlight_selected_source(self, label_id):
        """Визуально выделить выбранный источник"""
        for i, label in enumerate(self.labels):
            if i == label_id:
                # Выделяем выбранный источник
                label.setStyleSheet("border: 3px solid #00FF00; background-color: #F0F0F0;")
            else:
                # Снимаем выделение с остальных
                label.setStyleSheet("border: 1px solid black;")
    
    def _auto_select_source_for_zones(self):
        """Автоматически выбрать источник для Zone Editor"""
        try:
            # Проверяем, есть ли активные источники
            if not hasattr(self, 'labels') or not self.labels:
                return
            
            # Выбираем первый доступный источник
            if len(self.labels) > 0:
                # Активируем режим выбора источника для зон
                for label in self.labels:
                    label.add_zone_clicked(True)
                # Автоматически кликаем по первому источнику
                self.add_zone_signal.emit(0)
        except Exception as e:
            self.logger.error(f"Error auto-selecting source for zones: {e}")
    
    def _auto_select_source_for_roi(self):
        """Автоматически выбрать источник для ROI Editor"""
        try:
            # Проверяем, есть ли активные источники
            if not hasattr(self, 'labels') or not self.labels:
                return
            
            # Выбираем первый доступный источник
            if len(self.labels) > 0:
                # Активируем режим выбора источника для ROI
                for label in self.labels:
                    label.add_roi_clicked(True)
                # Автоматически кликаем по первому источнику
                self.add_roi_signal.emit(0)
        except Exception as e:
            self.logger.error(f"Error auto-selecting source for ROI: {e}")

    def _auto_select_source_for_roi_with_id(self, source_id):
        """Автоматически выбрать указанный источник для ROI Editor"""
        try:
            # Проверяем, есть ли активные источники
            if not hasattr(self, 'labels') or not self.labels:
                return
            
            # Находим label_id для указанного source_id
            label_id = None
            for label_idx, label in enumerate(self.labels):
                if self.labels_sources_ids.get(label_idx) == source_id:
                    label_id = label_idx
                    break
            
            if label_id is not None:
                # Активируем режим выбора источника для ROI
                for label in self.labels:
                    label.add_roi_clicked(True)
                # Автоматически кликаем по указанному источнику
                self.add_roi_signal.emit(label_id)
                # Обновляем последний активный источник
                self.last_active_source_id = source_id
            else:
                self.logger.warning(f"Source {source_id} not found, using first available")
                self._auto_select_source_for_roi()
        except Exception as e:
            self.logger.error(f"Error auto-selecting source {source_id} for ROI: {e}")

    def _auto_select_source_for_zones_with_id(self, source_id):
        """Автоматически выбрать указанный источник для Zone Editor"""
        try:
            # Проверяем, есть ли активные источники
            if not hasattr(self, 'labels') or not self.labels:
                return
            
            # Находим label_id для указанного source_id
            label_id = None
            for label_idx, label in enumerate(self.labels):
                if self.labels_sources_ids.get(label_idx) == source_id:
                    label_id = label_idx
                    break
            
            if label_id is not None:
                # Активируем режим выбора источника для зон
                for label in self.labels:
                    label.add_zone_clicked(True)
                # Автоматически кликаем по указанному источнику
                self.add_zone_signal.emit(label_id)
                # Обновляем последний активный источник
                self.last_active_source_id = source_id
            else:
                self.logger.warning(f"Source {source_id} not found, using first available")
                self._auto_select_source_for_zones()
        except Exception as e:
            self.logger.error(f"Error auto-selecting source {source_id} for zones: {e}")
    
    def get_current_source_info(self):
        """Получить информацию о текущем выбранном источнике"""
        try:
            if not hasattr(self, 'labels') or not self.labels:
                return None
            
            # Возвращаем информацию о первом источнике как текущем
            if len(self.labels) > 0:
                return {
                    'source_id': self.labels_sources_ids.get(0, 0),
                    'label_id': 0,
                    'is_active': True
                }
            return None
        except Exception as e:
            self.logger.error(f"Error getting current source info: {e}")
            return None

    def closeEvent(self, event):
        if self.controller.enable_close_from_gui:
            self.controller.release()
            self.zone_window.close()
            if self.db_journal_win is not None:
                self.db_journal_win.close()
            #with open(self.params_path, 'w') as params_file:
            #    json.dump(self.params, params_file, indent=4)
            QApplication.closeAllWindows()
            event.accept()
        else:
            self.setVisible(False)
            event.ignore()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.controller.set_current_main_widget_size(self.geometry().width()-self.toolbar_width, self.geometry().height()-self.menu_height)

    def check_controller_status(self):
        if not self.controller.is_running():
            self.close()

    @pyqtSlot()
    def add_channel_slot(self):  # Выбор источника для добавления зон
        #src_widget = SourceWidget(params=None, creds=None, parent=self)
        #src_widget.show()
        self.controller.add_channel()

    def _create_json_journal_window(self):
        """Create JSON journal window as fallback when database is not available"""
        # Get image_dir from database_config (even if database is disabled)
        images_dir = 'EvilEyeData'  # default
        if hasattr(self.controller, 'database_config') and self.controller.database_config.get('database', {}):
            images_dir = self.controller.database_config['database'].get('images_dir', images_dir)
        
        # Check if directory exists before creating journal
        if os.path.exists(images_dir):
            try:
                from . import json_journal
                self.db_journal_win = json_journal.JsonJournalWindow(self, self.params, images_dir, False,
                                                                    logger_name="json_journal", parent_logger=self.logger)
                self.db_journal_win.setVisible(False)
            except Exception as e:
                self.logger.error(f"JSON journal creation error: {e}")
                self.db_journal_win = None
        else:
            self.logger.warning(f"Images folder does not exist: {images_dir}")
            self.db_journal_win = None

    @pyqtSlot()
    def del_channel_slot(self):  # Выбор источника для добавления зон
        pass
    
    @pyqtSlot()
    def open_settings_window(self):
        """Открыть окно настроек как модальное окно"""
        try:
            # Если окно настроек уже открыто, показываем его
            if self.settings_window and not self.settings_window.isVisible():
                self.settings_window.show()
                self.settings_window.raise_()
                self.settings_window.activateWindow()
                return
            
            # Используем существующий файл конфигурации или создаем временный
            config_file_path = self.params_path
            if not os.path.exists(config_file_path):
                import tempfile
                import json
                
                # Создаем временный файл с текущей конфигурацией
                temp_dir = tempfile.gettempdir()
                temp_file = os.path.join(temp_dir, f"evileye_config_{os.getpid()}.json")
                
                with open(temp_file, 'w', encoding='utf-8') as f:
                    json.dump(self.params, f, indent=4, ensure_ascii=False)
                
                config_file_path = temp_file
                self.logger.info(f"Created temporary config file: {config_file_path}")
            
            # Проверяем, что файл существует
            if not os.path.exists(config_file_path):
                error_msg = f"Файл конфигурации не найден: {config_file_path}"
                self.logger.error(error_msg)
                QMessageBox.critical(
                    self,
                    "Ошибка",
                    error_msg
                )
                return
            
            # Создаем новое окно настроек
            # ConfigurerMainWindow ожидает относительный путь от корня проекта
            from evileye.utils.utils import get_project_root
            project_root = get_project_root()
            
            # Преобразуем абсолютный путь в относительный от корня проекта
            if os.path.isabs(config_file_path):
                # Если это абсолютный путь, делаем его относительным от корня проекта
                relative_path = os.path.relpath(config_file_path, project_root)
            else:
                # Если это уже относительный путь, используем как есть
                relative_path = config_file_path
            
            # Проверяем, что файл существует относительно корня проекта
            full_path = os.path.join(project_root, relative_path)
            if not os.path.exists(full_path):
                # Если файл не найден, попробуем найти его в родительской директории
                parent_root = os.path.dirname(project_root)
                parent_full_path = os.path.join(parent_root, relative_path)
                if os.path.exists(parent_full_path):
                    # Используем абсолютный путь к файлу в родительской директории
                    relative_path = os.path.relpath(parent_full_path, project_root)
                    self.logger.info(f"Found config file in parent directory, using relative path: {relative_path}")
                else:
                    error_msg = f"Файл конфигурации не найден: {full_path}"
                    self.logger.error(error_msg)
                    QMessageBox.critical(
                        self,
                        "Ошибка",
                        error_msg
                    )
                    return
            
            self.logger.info(f"Creating ConfigurerMainWindow with config_file_name: {relative_path}")
            self.settings_window = ConfigurerMainWindow(
                config_file_name=relative_path,
                win_width=1280,
                win_height=720,
                parent=self
            )
            self.logger.info("ConfigurerMainWindow created successfully")
            
            # Подключаем сигналы для обработки изменений конфигурации
            self.settings_window.config_changed.connect(self._on_settings_config_changed)
            self.settings_window.window_closed.connect(self._on_settings_window_closed)
            
            # Показываем окно
            self.settings_window.show()
            self.settings_window.raise_()
            self.settings_window.activateWindow()
            
            self.logger.info("Settings window opened")
            
        except Exception as e:
            self.logger.error(f"Error opening settings window: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть окно настроек:\n{str(e)}"
            )
    
    @pyqtSlot(str)
    def _on_settings_config_changed(self, config_file: str):
        """Обработчик изменения конфигурации в окне настроек"""
        if config_file == self.params_path:
            self.logger.info("Configuration changed in settings window")
            
            # Показываем диалог с вопросом о перезапуске
            reply = QMessageBox.question(
                self,
                "Изменение конфигурации",
                "Конфигурация была изменена в окне настроек.\n"
                "Для применения изменений необходимо перезапустить приложение.\n"
                "Хотите перезапустить сейчас?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes
            )
            
            if reply == QMessageBox.StandardButton.Yes:
                self._restart_application()
    
    @pyqtSlot()
    def _on_settings_window_closed(self):
        """Обработчик закрытия окна настроек"""
        self.settings_window = None
        self.logger.debug("Settings window closed")
    
    def _restart_application(self):
        """Перезапуск приложения с новой конфигурацией"""
        try:
            self.logger.info("Restarting application with new configuration")
            
            # Закрываем текущее приложение
            self.close()
            
            # Запускаем новое приложение
            import subprocess
            import sys
            from pathlib import Path
            
            # Получаем путь к process.py
            project_root = Path(__file__).parent.parent.parent
            process_script = project_root / "evileye" / "process.py"
            
            if process_script.exists():
                cmd = [sys.executable, str(process_script), "--config", self.params_path, "--gui"]
                subprocess.Popen(cmd, cwd=project_root)
            else:
                self.logger.error(f"process.py not found at {process_script}")
                
        except Exception as e:
            self.logger.error(f"Error restarting application: {e}")
            QMessageBox.critical(
                self,
                "Ошибка перезапуска",
                f"Не удалось перезапустить приложение:\n{str(e)}"
            )
    
    @pyqtSlot()
    def open_config_history_window(self):
        """Открыть окно истории конфигураций"""
        try:
            # Если окно уже создано, просто показываем его
            if self.config_history_window:
                if self.config_history_window.isVisible():
                    # Если окно уже видимо, просто активируем его
                    self.config_history_window.raise_()
                    self.config_history_window.activateWindow()
                else:
                    # Если окно скрыто, показываем его
                    self.config_history_window.show()
                    self.config_history_window.raise_()
                    self.config_history_window.activateWindow()
                return
            
            # Проверяем, есть ли доступ к базе данных
            if not hasattr(self, 'db_journal_win') or self.db_journal_win is None:
                QMessageBox.warning(
                    self,
                    "База данных недоступна",
                    "Для просмотра истории конфигураций необходимо подключение к базе данных.\n"
                    "Убедитесь, что в конфигурации указаны правильные параметры базы данных."
                )
                return
            
            # Проверяем тип журнала - нужен именно DatabaseJournalWindow
            if not hasattr(self.db_journal_win, 'db_controller'):
                QMessageBox.warning(
                    self,
                    "Режим JSON журнала",
                    "История конфигураций доступна только при использовании базы данных.\n"
                    "Текущий режим: JSON журнал.\n"
                    "Для доступа к истории конфигураций включите использование базы данных в настройках."
                )
                return
            
            # Инициализируем ConfigHistoryManager, если еще не инициализирован
            if not self.config_history_manager:
                try:
                    # Получаем DatabaseController из db_journal_win
                    db_controller = self.db_journal_win.db_controller
                    if db_controller:
                        self.config_history_manager = ConfigHistoryManager(db_controller)
                        self.logger.info("ConfigHistoryManager initialized")
                    else:
                        QMessageBox.warning(
                            self,
                            "Ошибка",
                            "Не удалось получить доступ к контроллеру базы данных."
                        )
                        return
                except Exception as e:
                    self.logger.error(f"Error initializing ConfigHistoryManager: {e}")
                    QMessageBox.critical(
                        self,
                        "Ошибка",
                        f"Не удалось инициализировать менеджер истории конфигураций:\n{str(e)}"
                    )
                    return
            
            # Создаем новое окно истории конфигураций только один раз
            self.config_history_window = JobsHistory(self)
            
            # Устанавливаем ConfigHistoryManager
            self.config_history_window.set_config_history_manager(self.config_history_manager)
            
            # Настраиваем окно
            self.config_history_window.setWindowTitle("История конфигураций")
            self.config_history_window.setMinimumSize(1200, 800)
            
            # Показываем окно
            self.config_history_window.show()
            self.config_history_window.raise_()
            self.config_history_window.activateWindow()
            
            self.logger.info("Configuration history window opened")
            
        except Exception as e:
            self.logger.error(f"Error opening config history window: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть окно истории конфигураций:\n{str(e)}"
            )

    # Visual Editors methods
    def _open_roi_editor_with_source(self, source_id=None):
        """Единый метод для открытия ROI Editor (окно) с указанным источником"""
        try:
            self.logger.info("=== ENTERING _open_roi_editor_with_source (window) ===")
            if self.roi_editor_window is None:
                # Пытаемся создать окно лениво при первом открытии
                try:
                    self.roi_editor_window = ROIEditorWindow(self.params)
                    self.roi_editor_window.roi_updated.connect(lambda rois: None)
                    self.roi_editor_window.roi_editor_closed.connect(self._on_roi_editor_closed)
                    self.roi_editor_window.setVisible(False)
                    self.logger.info("ROIEditorWindow lazily initialized")
                except Exception as e:
                    self.logger.error(f"ROIEditorWindow lazy init failed: {e}")
                    return

            if not hasattr(self, 'labels') or not self.labels:
                self.logger.warning("No active sources available for ROI Editor")
                return

            if source_id is None:
                source_id = self.last_active_source_id if self.last_active_source_id is not None else 0

            clean_cv_image = self.last_clean_cv_images.get(source_id)
            if clean_cv_image is None:
                self.logger.error(f"No clean CV image available for source {source_id}")
                return

            # Разрешаем только для PipelineSurveillance
            if not (self.controller and hasattr(self.controller, 'pipeline') and self.controller.pipeline and self.controller.pipeline.__class__.__name__ == 'PipelineSurveillance'):
                self.logger.warning("ROI Editor is supported only for PipelineSurveillance. Operation cancelled.")
                return

            # Если окно уже открыто — закрываем, чтобы сработал closeEvent
            if self.roi_editor_window.isVisible():
                self.logger.info("Closing ROI Editor window to trigger save flow (closeEvent)")
                self.roi_editor_window.close()
                return

            # Ищем живой детектор по source_id в пайплайне, возвращаем (instance, index)
            det_instance, detector_index = self._find_pipeline_detector_for_source(source_id)
            # Логируем состав детекторов
            try:
                if hasattr(self.controller.pipeline, 'get_detectors'):
                    dets = self.controller.pipeline.get_detectors()
                else:
                    dets = getattr(self.controller.pipeline, 'detectors', [])
                self.logger.info(f"Pipeline detectors count: {len(dets) if dets is not None else 0}")
                for i, d in enumerate(dets or []):
                    ids = d.get_source_ids() if hasattr(d, 'get_source_ids') else getattr(d, 'source_ids', [])
                    self.logger.info(f"Detector[{i}] class={getattr(d,'__class__', type(d))}, source_ids={ids}")
            except Exception:
                pass
            if det_instance is None:
                self.logger.warning(f"No live detector found for source {source_id}; aborting ROI Editor open")
                return

            # Сохраняем ссылку для будущего применения
            self._roi_editor_detector = det_instance

            # Контекст окна
            self.roi_editor_window.set_context(source_id, detector_index if detector_index is not None else -1)
            self.logger.info("Setting ROI editor window visible")
            # Убираем родительское окно для независимого отображения
            self.roi_editor_window.setParent(None)
            # Устанавливаем как независимое окно
            self.roi_editor_window.setWindowFlags(self.roi_editor_window.windowFlags() | Qt.WindowType.Window)
            # Принудительно устанавливаем размер и позицию
            self.roi_editor_window.resize(1200, 800)
            self.roi_editor_window.move(100, 100)
            self.roi_editor_window.setVisible(True)
            self.roi_editor_window.raise_()
            self.roi_editor_window.activateWindow()
            # Принудительно обновляем окно
            self.roi_editor_window.update()
            self.roi_editor_window.repaint()
            self.logger.info("ROI editor window activated")
            self.roi_editor_window.set_cv_image(source_id, clean_cv_image)
            self.logger.info("CV image set in ROI editor")

            # ROI читаем только из живого детектора
            try:
                rois_xywh = det_instance.get_rois_for_source(source_id) if hasattr(det_instance, 'get_rois_for_source') else []
                self.logger.info(f"Loaded {len(rois_xywh) if rois_xywh else 0} ROI from live detector for source {source_id}")
            except Exception as e:
                self.logger.error(f"Error getting ROIs from live detector: {e}")
                rois_xywh = []

            # Нормализуем до [[x,y,w,h], ...]
            norm = []
            for r in rois_xywh or []:
                if isinstance(r, (list, tuple)) and len(r) == 4:
                    norm.append([int(r[0]), int(r[1]), int(r[2]), int(r[3])])
            self.logger.info(f"Setting {len(norm)} ROI from detector")
            self.roi_editor_window.set_rois_from_detector(norm)
            self.logger.info("ROI set successfully")
            self.current_roi_source_id = source_id
            self.logger.info("ROI Editor window setup completed")
            # Проверяем, что окно действительно видимо
            if self.roi_editor_window.isVisible():
                self.logger.info("ROI Editor window is visible")
                # Принудительно показываем окно
                self.roi_editor_window.show()
                self.roi_editor_window.raise_()
                self.roi_editor_window.activateWindow()
            else:
                self.logger.warning("ROI Editor window is not visible")
                # Пытаемся принудительно показать
                self.roi_editor_window.show()
                self.roi_editor_window.raise_()
                self.roi_editor_window.activateWindow()
        except Exception as e:
            self.logger.error(f"Error opening ROI Editor window: {e}")

    def _find_first_detector_index_for_source(self, source_id: int):
        try:
            detectors = []
            if isinstance(self.params, dict) and 'detectors' in self.params:
                detectors = self.params['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], dict) and 'detectors' in self.params['pipeline']:
                detectors = self.params['pipeline']['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], list):
                detectors = self.params['pipeline']
            for i, det in enumerate(detectors):
                if source_id in det.get('source_ids', []):
                    return i
        except Exception:
            pass
        return None

    def _get_rois_from_detector(self, detector_index: int|None, source_id: int):
        try:
            if detector_index is None or detector_index < 0:
                return []
            # Предпочтительно получать реальный объект детектора из контроллера, если он есть
            if hasattr(self.controller, 'pipeline') and self.controller.pipeline:
                det = self._get_pipeline_detector_by_index(detector_index)
                if det and hasattr(det, 'get_rois_for_source'):
                    return det.get_rois_for_source(source_id)
            # Fallback: из params, если детектор не инициализирован
            detectors = []
            if 'detectors' in self.params:
                detectors = self.params['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], dict) and 'detectors' in self.params['pipeline']:
                detectors = self.params['pipeline']['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], list):
                detectors = self.params['pipeline']
            det_cfg = detectors[detector_index] if detector_index < len(detectors) else None
            if det_cfg:
                roi = det_cfg.get('roi', [[]])
                src_ids = det_cfg.get('source_ids', [])
                # Если у детектора указан список source_ids, попробуем найти индекс
                if isinstance(src_ids, list) and source_id in src_ids and isinstance(roi, list) and len(roi) > 0:
                    idx = src_ids.index(source_id)
                    if idx < len(roi) and isinstance(roi[idx], list):
                        return roi[idx]
                # Иначе, если roi един для всех источников, берём первый
                if isinstance(roi, list) and len(roi) > 0 and isinstance(roi[0], list):
                    return roi[0]
            return []
        except Exception:
            return []

    def _get_pipeline_detector_by_index(self, detector_index: int):
        det = None
        try:
            if hasattr(self.controller, 'pipeline') and self.controller.pipeline:
                try:
                    det = self.controller.pipeline.get_detector_by_index(detector_index)
                except Exception:
                    pass
                if det is None and hasattr(self.controller.pipeline, 'detectors') and isinstance(self.controller.pipeline.detectors, list):
                    if 0 <= detector_index < len(self.controller.pipeline.detectors):
                        det = self.controller.pipeline.detectors[detector_index]
        except Exception:
            det = None
        return det

    def _find_pipeline_detector_for_source(self, source_id: int):
        """Возвращает (detector_instance, index) для первого детектора, содержащего source_id."""
        try:
            if hasattr(self.controller, 'pipeline') and self.controller.pipeline and hasattr(self.controller.pipeline, 'detectors'):
                for i, d in enumerate(self.controller.pipeline.detectors):
                    try:
                        src_ids = d.get_source_ids() if hasattr(d, 'get_source_ids') else getattr(d, 'source_ids', [])
                        self.logger.info(f"Pipeline detector[{i}]: class={getattr(d,'__class__', type(d))}, source_ids={src_ids}")
                        if source_id in src_ids:
                            self.logger.info(f"Matched pipeline detector[{i}] for source {source_id}")
                            return d, i
                    except Exception:
                        continue
        except Exception:
            pass
        return None, None

    def _on_roi_editor_closed(self, rois_xyxy: list, source_id: int, detector_index: int, accepted: bool):
        """Обновление ROI в детекторе после закрытия окна редактора."""
        try:
            self.logger.info(f"ROI editor closed: accepted={accepted}, source_id={source_id}, detector_index={detector_index}, rois_count={len(rois_xyxy) if rois_xyxy else 0}")
            if not accepted:
                return

            # Найдём детектор для применения ROI
            det = None
            # 1) Если индекс валиден — пробуем по индексу
            if detector_index is not None and detector_index >= 0 and hasattr(self.controller, 'pipeline') and self.controller.pipeline:
                try:
                    det = self.controller.pipeline.get_detector_by_index(detector_index)
                except Exception:
                    det = None
                if det is None and hasattr(self.controller.pipeline, 'detectors') and isinstance(self.controller.pipeline.detectors, list):
                    if 0 <= detector_index < len(self.controller.pipeline.detectors):
                        det = self.controller.pipeline.detectors[detector_index]

            # 2) Если не нашли — используем сохранённую ссылку
            if det is None and hasattr(self, '_roi_editor_detector') and self._roi_editor_detector is not None:
                det = self._roi_editor_detector
                self.logger.info("Using stored detector reference for ROI apply")

            # 3) Если всё ещё не нашли — ищем по source_id
            if det is None and hasattr(self.controller, 'pipeline') and self.controller.pipeline and hasattr(self.controller.pipeline, 'detectors'):
                for i, d in enumerate(self.controller.pipeline.detectors):
                    try:
                        src_ids = d.get_source_ids() if hasattr(d, 'get_source_ids') else getattr(d, 'source_ids', [])
                        if source_id in src_ids:
                            det = d
                            detector_index = i
                            self.logger.info(f"Resolved detector by source_id: index={i}")
                            break
                    except Exception:
                        continue

            # Применяем, если нашли детектор с нужным API
            if det is not None and hasattr(det, 'set_rois_for_source'):
                det.set_rois_for_source(int(source_id), rois_xyxy)
                self.logger.info(f"Applied {len(rois_xyxy)} ROI to detector index {detector_index} for source {source_id} (det={getattr(det,'__class__', type(det))})")
                if hasattr(det, '_on_rois_updated_for_source'):
                    try:
                        det._on_rois_updated_for_source(int(source_id))
                    except Exception:
                        pass
                # Централизованное сохранение конфигурации после применения ROI
                try:
                    if hasattr(self, 'controller') and hasattr(self.controller, 'save_config'):
                        if not getattr(self.controller, 'params_path', None):
                            self.controller.params_path = self.params_path
                        self.controller.save_config()
                except Exception:
                    pass
            else:
                self.logger.warning("Detector instance not available; ROI not applied")
        except Exception as e:
            self.logger.error(f"Error applying ROI to detector on editor close: {e}")

    def _open_zone_editor_with_source(self, source_id=None):
        """Единый метод для открытия Zone Editor с указанным источником"""
        try:
            # Проверяем, есть ли активные источники
            if not hasattr(self, 'labels') or not self.labels:
                self.logger.warning("No active sources available for Zone Editor")
                return
            
            # Определяем source_id из последнего выбранного источника
            if source_id is None:
                source_id = self.last_active_source_id if self.last_active_source_id is not None else 0
            
            self.logger.info(f"Opening Zone Editor for source: {source_id}")
            
            # Получаем чистое OpenCV изображение для источника (без нарисованных элементов)
            clean_cv_image = self.last_clean_cv_images.get(source_id)
            
            # Если нет в кэше, пытаемся получить из VideoThread
            if clean_cv_image is None:
                clean_cv_image = self._get_clean_image_from_thread(source_id)
            
            # Проверяем наличие чистого OpenCV изображения
            if clean_cv_image is None:
                self.logger.error(f"No clean OpenCV image available for source {source_id}")
                return
            
            self.logger.info(f"Using clean OpenCV image for source {source_id}")
            
            # Открываем Zone Editor
            if self.zone_window.isVisible():
                self.zone_window.setVisible(False)
            else:
                self.zone_window.setVisible(True)
                # Устанавливаем OpenCV изображение
                self.zone_window.set_cv_image(source_id, clean_cv_image)
                
                # Попробуем получить детекторы из pipeline для зон
                pipeline_params = self._get_detectors_from_pipeline()
                if pipeline_params:
                    self.logger.info(f"Using pipeline params for zones: {len(pipeline_params.get('detectors', []))}")
                    # Обновляем self.params для zone_window
                    self.params.update(pipeline_params)
                
                # Загружаем зоны из конфигурации
                zones_data = self.zone_window.get_zones_for_source(source_id)
                
                # Сохраняем текущий source_id
                self.current_zone_source_id = source_id
            
        except Exception as e:
            self.logger.error(f"Error opening Zone Editor with source: {e}")

    @pyqtSlot()
    def open_roi_editor_window(self):
        """Открыть ROI Editor из меню"""
        self._open_roi_editor_with_source()

    @pyqtSlot()
    def open_zone_editor_window(self):
        """Открыть Zone Editor из меню"""
        self._open_zone_editor_with_source()

    @pyqtSlot()
    def open_class_mapping_editor_window(self):
        """Открыть Class Mapping Editor"""
        try:
            # Получаем текущий маппинг классов из конфигурации
            current_mapping = {}
            if hasattr(self, 'params') and 'detectors' in self.params:
                for detector_id, detector_config in self.params['detectors'].items():
                    if 'class_mapping' in detector_config:
                        current_mapping.update(detector_config['class_mapping'])
            
            dialog = ClassMappingDialog(self, current_mapping)
            dialog.class_mapping_updated.connect(self._on_class_mapping_updated)
            dialog.exec()
        except Exception as e:
            self.logger.error(f"Error opening Class Mapping Editor: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Не удалось открыть Class Mapping Editor:\n{str(e)}"
            )

    # Tools methods
    @pyqtSlot()
    def validate_current_config(self):
        """Валидация текущей конфигурации"""
        try:
            if not hasattr(self, 'params'):
                QMessageBox.warning(self, "Ошибка", "Конфигурация не загружена")
                return
            
            # Используем ConfigHistoryManager для валидации
            if self.config_history_manager:
                validation_result = self.config_history_manager.validate_config(self.params)
                
                if validation_result['valid']:
                    message = "Конфигурация валидна!"
                    if validation_result['warnings']:
                        message += f"\n\nПредупреждения ({validation_result['warning_count']}):\n"
                        message += "\n".join(f"• {warning}" for warning in validation_result['warnings'])
                    
                    QMessageBox.information(self, "Валидация", message)
                else:
                    message = f"Найдены ошибки ({validation_result['error_count']}):\n"
                    message += "\n".join(f"• {error}" for error in validation_result['errors'])
                    
                    if validation_result['warnings']:
                        message += f"\n\nПредупреждения ({validation_result['warning_count']}):\n"
                        message += "\n".join(f"• {warning}" for warning in validation_result['warnings'])
                    
                    QMessageBox.warning(self, "Ошибки валидации", message)
            else:
                QMessageBox.warning(self, "Ошибка", "ConfigHistoryManager не инициализирован")
                
        except Exception as e:
            self.logger.error(f"Error validating config: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка валидации конфигурации:\n{str(e)}"
            )

    @pyqtSlot()
    def export_current_config(self):
        """Экспорт текущей конфигурации"""
        try:
            if not hasattr(self, 'params'):
                QMessageBox.warning(self, "Ошибка", "Конфигурация не загружена")
                return
            
            from PyQt6.QtWidgets import QFileDialog
            
            file_path, _ = QFileDialog.getSaveFileName(
                self,
                "Экспорт конфигурации",
                "config_export.json",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(self.params, f, indent=2, ensure_ascii=False)
                
                QMessageBox.information(
                    self,
                    "Успех",
                    f"Конфигурация экспортирована в:\n{file_path}"
                )
                
        except Exception as e:
            self.logger.error(f"Error exporting config: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка экспорта конфигурации:\n{str(e)}"
            )

    @pyqtSlot()
    def import_config_from_file(self):
        """Импорт конфигурации из файла"""
        try:
            from PyQt6.QtWidgets import QFileDialog
            
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "Импорт конфигурации",
                "",
                "JSON Files (*.json);;All Files (*)"
            )
            
            if file_path:
                with open(file_path, 'r', encoding='utf-8') as f:
                    imported_config = json.load(f)
                
                # Валидируем импортированную конфигурацию
                if self.config_history_manager:
                    validation_result = self.config_history_manager.validate_config(imported_config)
                    
                    if not validation_result['valid']:
                        message = f"Импортированная конфигурация содержит ошибки ({validation_result['error_count']}):\n"
                        message += "\n".join(f"• {error}" for error in validation_result['errors'])
                        
                        reply = QMessageBox.question(
                            self,
                            "Ошибки в конфигурации",
                            f"{message}\n\nПродолжить импорт?",
                            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                        )
                        
                        if reply == QMessageBox.StandardButton.No:
                            return
                
                # Подтверждаем импорт
                reply = QMessageBox.question(
                    self,
                    "Подтверждение импорта",
                    f"Импортировать конфигурацию из {file_path}?\n\n"
                    f"Текущая конфигурация будет заменена.",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                
                if reply == QMessageBox.StandardButton.Yes:
                    self.params = imported_config
                    QMessageBox.information(
                        self,
                        "Успех",
                        "Конфигурация успешно импортирована.\n"
                        "Перезапустите приложение для применения изменений."
                    )
                
        except Exception as e:
            self.logger.error(f"Error importing config: {e}")
            QMessageBox.critical(
                self,
                "Ошибка",
                f"Ошибка импорта конфигурации:\n{str(e)}"
            )

    # Signal handlers for visual editors
    @pyqtSlot(list)
    def _on_roi_updated(self, rois):
        """Обработка обновления ROI"""
        try:
            self.logger.info(f"ROI updated: {len(rois)} regions")
            
            # Сохраняем ROI в конфигурацию
            if hasattr(self, 'current_roi_source_id') and self.current_roi_source_id is not None:
                self._save_rois_to_config(rois, self.current_roi_source_id)
                self._save_config_to_file()
        except Exception as e:
            self.logger.error(f"Error updating ROI: {e}")

    @pyqtSlot(list)
    def _on_zones_updated(self, zones):
        """Обработка обновления зон"""
        try:
            self.logger.info(f"Zones updated: {len(zones)} zones")
            
            # Сохраняем зоны в конфигурацию
            if hasattr(self, 'current_zone_source_id') and self.current_zone_source_id is not None:
                self._save_zones_to_config(zones, self.current_zone_source_id)
                self._save_config_to_file()
        except Exception as e:
            self.logger.error(f"Error updating zones: {e}")
    
    @pyqtSlot(dict, int, bool)
    def _on_zone_editor_closed(self, zones_dict, source_id, accepted):
        """Обработка закрытия редактора зон"""
        try:
            self.logger.info(f"Zone editor closed for source {source_id}, accepted: {accepted}")
            
            if accepted:
                # Пользователь принял изменения - сохраняем зоны
                # zones_dict содержит {source_id: zones_data}
                zones_data = zones_dict.get(str(source_id), [])
                self._save_zones_to_config(zones_data, source_id)
                self._save_config_to_file()
                self.logger.info(f"Zones saved for source {source_id}")
            else:
                # Пользователь отклонил изменения - зоны уже восстановлены в ZoneWindow
                self.logger.info(f"Zone changes rejected for source {source_id}")
            
            # Обновляем отображение зон
            if hasattr(self, 'toggle_zones') and self.toggle_zones.isChecked():
                zones = {}
                if hasattr(self, 'zone_window') and self.zone_window:
                    try:
                        zones = self.zone_window.get_zone_info()
                    except Exception:
                        zones = {}
                self.display_zones_signal.emit(zones)
                
        except Exception as e:
            self.logger.error(f"Error handling zone editor close: {e}")

    @pyqtSlot(dict)
    def _on_class_mapping_updated(self, class_mapping):
        """Обработка обновления маппинга классов"""
        try:
            self.logger.info(f"Class mapping updated: {len(class_mapping)} classes")
            
            # Сохраняем маппинг классов в конфигурацию
            self._save_class_mapping_to_config(class_mapping)
            self._save_config_to_file()
        except Exception as e:
            self.logger.error(f"Error updating class mapping: {e}")

    def _save_rois_to_config(self, rois, source_id):
        """Сохранить ROI в конфигурацию для указанного источника"""
        try:
            # Находим детектор для данного источника
            detectors = []
            
            # Проверяем разные возможные места для детекторов
            if 'detectors' in self.params:
                detectors = self.params['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], dict) and 'detectors' in self.params['pipeline']:
                detectors = self.params['pipeline']['detectors']
            elif 'pipeline' in self.params and isinstance(self.params['pipeline'], list):
                detectors = self.params['pipeline']
            
            for detector in detectors:
                detector_source_ids = detector.get('source_ids', [])
                if source_id in detector_source_ids:
                    # Конвертируем ROI в формат конфигурации
                    roi_coords = []
                    for roi in rois:
                        coords = roi.get("coords", [])
                        if len(coords) == 4:
                            roi_coords.append(coords)
                    
                    # Обновляем ROI в конфигурации
                    detector['roi'] = [roi_coords]  # ROI хранится как список списков
                    self.logger.info(f"Saved {len(roi_coords)} ROI for source {source_id}")
                    break
            # После локального обновления параметров — централизованное сохранение через контроллер
            try:
                if hasattr(self, 'controller') and hasattr(self.controller, 'save_config'):
                    # Контроллер должен знать путь params_path, пробросим при необходимости
                    if not getattr(self.controller, 'params_path', None):
                        self.controller.params_path = self.params_path
                    self.controller.save_config()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Error saving ROI to config: {e}")

    def _save_zones_to_config(self, zones_data, source_id):
        """Сохранить зоны в конфигурацию для указанного источника"""
        try:
            # Инициализируем структуру если её нет
            if 'events_detectors' not in self.params:
                self.params['events_detectors'] = {}
            if 'ZoneEventsDetector' not in self.params['events_detectors']:
                self.params['events_detectors']['ZoneEventsDetector'] = {'sources': {}}
            if 'sources' not in self.params['events_detectors']['ZoneEventsDetector']:
                self.params['events_detectors']['ZoneEventsDetector']['sources'] = {}
            
            # zones_data уже в правильном формате (список координат зон)
            # Просто сохраняем их в конфигурацию
            self.params['events_detectors']['ZoneEventsDetector']['sources'][str(source_id)] = zones_data
            self.logger.info(f"Saved {len(zones_data)} zones for source {source_id}")
            
            # Централизованное сохранение через контроллер
            try:
                if hasattr(self, 'controller') and hasattr(self.controller, 'save_config'):
                    if not getattr(self.controller, 'params_path', None):
                        self.controller.params_path = self.params_path
                    self.controller.save_config()
            except Exception:
                pass
        except Exception as e:
            self.logger.error(f"Error saving zones to config: {e}")

    def _save_class_mapping_to_config(self, class_mapping):
        """Сохранить маппинг классов в конфигурацию"""
        try:
            # Обновляем маппинг классов в каждом детекторе
            detectors = self.params.get('detectors', [])
            for detector in detectors:
                detector['class_mapping'] = class_mapping
            self.logger.info(f"Saved class mapping with {len(class_mapping)} classes")
        except Exception as e:
            self.logger.error(f"Error saving class mapping to config: {e}")

    def _save_config_to_file(self):
        """Сохранить конфигурацию в файл"""
        try:
            if hasattr(self, 'params_path') and self.params_path:
                import json
                with open(self.params_path, 'w', encoding='utf-8') as f:
                    json.dump(self.params, f, indent=4, ensure_ascii=False)
                self.logger.info(f"Configuration saved to {self.params_path}")
        except Exception as e:
            self.logger.error(f"Error saving config to file: {e}")
    
    def _get_detectors_from_pipeline(self):
        """Получить детекторы из pipeline"""
        try:
            self.logger.info(f"Controller available: {self.controller is not None}")
            if self.controller:
                self.logger.info(f"Controller has pipeline attr: {hasattr(self.controller, 'pipeline')}")
                if hasattr(self.controller, 'pipeline'):
                    self.logger.info(f"Pipeline is not None: {self.controller.pipeline is not None}")
            
            if self.controller and hasattr(self.controller, 'pipeline') and self.controller.pipeline:
                self.logger.info("Getting detectors from pipeline...")
                pipeline_params = self.controller.pipeline.get_params()
                self.logger.info(f"Pipeline params keys: {list(pipeline_params.keys())}")
                
                # Проверяем, есть ли детекторы в pipeline
                if 'detectors' in pipeline_params:
                    detectors = pipeline_params['detectors']
                    self.logger.info(f"Found {len(detectors)} detectors in pipeline")
                    
                    # Логируем информацию о каждом детекторе
                    for i, detector in enumerate(detectors):
                        self.logger.info(f"Detector {i}: {detector.get('type', 'Unknown')}")
                        self.logger.info(f"  Source IDs: {detector.get('source_ids', [])}")
                        self.logger.info(f"  ROI: {detector.get('roi', [])}")
                        
                        # Дополнительная информация о ROI
                        roi_data = detector.get('roi', [])
                        if roi_data:
                            self.logger.info(f"  ROI structure: {type(roi_data)} with {len(roi_data)} elements")
                            if len(roi_data) > 0:
                                self.logger.info(f"  First ROI element: {roi_data[0]}")
                    
                    return pipeline_params
                else:
                    self.logger.info("No detectors found in pipeline params")
                    return None
            else:
                self.logger.info("No pipeline available in controller")
                return None
        except Exception as e:
            self.logger.error(f"Error getting detectors from pipeline: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")
            return None
    
    def _get_clean_image_from_thread(self, source_id):
        """Получить чистое изображение из VideoThread для указанного источника"""
        try:
            if hasattr(self.controller, 'visualizer') and self.controller.visualizer:
                visualizer = self.controller.visualizer
                if hasattr(visualizer, 'visual_threads') and visualizer.visual_threads:
                    # Находим VideoThread для указанного source_id
                    for thread in visualizer.visual_threads:
                        if hasattr(thread, 'source_id') and thread.source_id == source_id:
                            clean_image = thread.get_clean_image()
                            if clean_image is not None:
                                self.logger.info(f"Retrieved clean image from VideoThread for source {source_id}")
                                return clean_image
                            break
        except Exception as e:
            self.logger.error(f"Error getting clean image from thread: {e}")
        return None
    
    def _log_all_detector_info(self):
        """Логировать информацию о всех доступных детекторах"""
        try:
            self.logger.info("=== DETECTOR INFORMATION ===")
            
            # 1. Проверяем self.params
            self.logger.info("1. Checking self.params:")
            if isinstance(self.params, dict):
                self.logger.info(f"   Keys: {list(self.params.keys())}")
                if 'detectors' in self.params:
                    detectors = self.params['detectors']
                    self.logger.info(f"   Detectors count: {len(detectors)}")
                    for i, detector in enumerate(detectors):
                        self.logger.info(f"   Detector {i}: {detector}")
                else:
                    self.logger.info("   No 'detectors' key in self.params")
                
                # Проверяем pipeline
                if 'pipeline' in self.params:
                    pipeline = self.params['pipeline']
                    self.logger.info(f"   Pipeline type: {type(pipeline)}")
                    if isinstance(pipeline, dict):
                        self.logger.info(f"   Pipeline keys: {list(pipeline.keys())}")
                        if 'detectors' in pipeline:
                            detectors = pipeline['detectors']
                            self.logger.info(f"   Pipeline detectors count: {len(detectors)}")
                            for i, detector in enumerate(detectors):
                                self.logger.info(f"   Pipeline Detector {i}: {detector}")
                    elif isinstance(pipeline, list):
                        self.logger.info(f"   Pipeline is list with {len(pipeline)} items")
                        for i, item in enumerate(pipeline):
                            self.logger.info(f"   Pipeline item {i}: {item}")
            else:
                self.logger.info(f"   self.params is not a dict: {type(self.params)}")
            
            # 2. Проверяем pipeline
            self.logger.info("2. Checking pipeline:")
            pipeline_params = self._get_detectors_from_pipeline()
            if pipeline_params:
                self.logger.info("   Pipeline params retrieved successfully")
            else:
                self.logger.info("   No pipeline params available")
            
            # 3. Проверяем файл конфигурации
            self.logger.info("3. Checking config file:")
            try:
                import json
                with open(self.params_path, 'r', encoding='utf-8') as f:
                    file_params = json.load(f)
                self.logger.info(f"   File keys: {list(file_params.keys())}")
                if 'detectors' in file_params:
                    detectors = file_params['detectors']
                    self.logger.info(f"   File detectors count: {len(detectors)}")
                else:
                    self.logger.info("   No 'detectors' key in file")
            except Exception as e:
                self.logger.error(f"   Error reading config file: {e}")
            
            self.logger.info("=== END DETECTOR INFORMATION ===")
        except Exception as e:
            self.logger.error(f"Error in _log_all_detector_info: {e}")
            import traceback
            self.logger.error(f"Traceback: {traceback.format_exc()}")

    @pyqtSlot(bool)
    def _toggle_display_zones(self, enabled: bool):
        try:
            if 'visualizer' not in self.params:
                self.params['visualizer'] = {}
            self.params['visualizer']['display_zones'] = enabled
            # Apply live
            if hasattr(self.controller, 'visualizer') and self.controller.visualizer:
                try:
                    self.controller.visualizer.display_zones = enabled
                except Exception:
                    pass
            # Emit zones or clear depending on state
            if enabled:
                zones = {}
                if hasattr(self, 'zone_window') and self.zone_window:
                    try:
                        zones = self.zone_window.get_zone_info()
                    except Exception:
                        zones = {}
                self.display_zones_signal.emit(zones)
            else:
                self.display_zones_signal.emit({})
            # Save via controller
            if hasattr(self.controller, 'save_config'):
                if not getattr(self.controller, 'params_path', None):
                    self.controller.params_path = self.params_path
                self.controller.params = self.params
                self.controller.save_config()
        except Exception as e:
            self.logger.error(f"Error toggling display_zones: {e}")