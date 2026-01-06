try:
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem
    )
    from PyQt6.QtGui import QPixmap, QIcon
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
        QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView,
        QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem
    )
    from PyQt5.QtGui import QPixmap, QIcon
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5

import sys
from pathlib import Path
from ..database_controller import database_controller_pg
from .journal_adapters.jadapter_fov_events import JournalAdapterFieldOfViewEvents
from .journal_adapters.jadapter_cam_events import JournalAdapterCamEvents
from .journal_adapters.jadapter_zone_events import JournalAdapterZoneEvents
from .journal_adapters.jadapter_system_events import JournalAdapterSystemEvents
from .journal_data_source_db import DatabaseJournalDataSource
from .unified_objects_journal import UnifiedObjectsJournal
from .unified_events_journal import UnifiedEventsJournal
from ..core.logger import get_module_logger
import logging

sys.path.append(str(Path(__file__).parent.parent.parent))


class DatabaseJournalWindow(QWidget):
    def __init__(self, main_window, close_app: bool = False, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        base_name = "evileye.db_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.logger.info("DatabaseJournalWindow.__init__ started")
        self.main_window = main_window
        self.params = {}
        self.database_params = {}
        self.close_app = close_app
        
        # Инициализация пустого UI
        self.db_controller = None
        self.adapter_params = {}
        self.db_params = {}
        self.vis_params = {}
        self.obj_journal_enabled = True
        self.tables = {}
        self.database_available = False
        
        # Адаптеры будут созданы в set_db_controller
        self.cam_events_adapter = None
        self.perimeter_events_adapter = None
        self.zone_events_adapter = None
        self.attr_events_adapter = None
        self.system_events_adapter = None

        self.logger.info("Setting up window and tabs...")
        self.setWindowTitle('DB Journal')
        self.resize(1600, 600)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        # Connect tab change signal for lazy journal creation
        self.tabs.currentChanged.connect(self._on_tab_changed)
        
        # Track which journals have been created
        self._objects_journal_created = False
        self._events_journal_created = False
        
        # Flag to prevent journal creation during initial tab setup
        self._initializing_tabs = False

        self.logger.info("Setting up layout...")
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)
        self.logger.info("DatabaseJournalWindow.__init__ completed")
    
    def set_db_controller(self, db_controller, params, database_params):
        """Установить данные из controller (вызывается после controller.init())"""
        self.logger.info("DatabaseJournalWindow.set_db_controller started")
        self.params = params
        self.database_params = database_params
        
        # Используем утилиту для обеспечения полноты database_params
        from evileye.utils.database_config_utils import ensure_database_config_complete
        
        # Логируем структуру database_params для отладки
        self.logger.info(f"database_params keys: {list(self.database_params.keys()) if self.database_params else 'None'}")
        
        # Убеждаемся, что database_params содержит все необходимые ключи
        self.database_params = ensure_database_config_complete(self.database_params)
        
        # Проверяем наличие обязательных ключей после дополнения
        if 'database_adapters' not in self.database_params or 'database' not in self.database_params:
            self.logger.error("database_params is incomplete after ensuring completeness")
            return
            
        self.adapter_params = self.database_params['database_adapters']
        self.db_params = self.database_params['database']
        self.vis_params = self.params.get('visualizer', {})
        self.obj_journal_enabled = self.vis_params.get('objects_journal_enabled', True)
        
        # Use provided db_controller
        if db_controller is not None:
            self.logger.info("Using provided DatabaseControllerPg instance")
            self.db_controller = db_controller
            self.tables = self.db_params.get('tables', {})
            self.database_available = True
        else:
            self.logger.warning("No db_controller provided")
            self.db_controller = None
            self.tables = {}
            self.database_available = False
            return

        # Process events periodically to keep GUI responsive during initialization
        try:
            from PyQt6.QtWidgets import QApplication
        except ImportError:
            from PyQt5.QtWidgets import QApplication
        
        # Инициализируем адаптеры и создаем вкладки
        self._init_adapters()
        self._create_journal_tabs()
        
        self.logger.info("DatabaseJournalWindow.set_db_controller completed")
    
    def _init_adapters(self):
        """Инициализировать адаптеры событий"""
        if not self.db_controller or not self.adapter_params:
            return
            
        self.logger.info("Initializing event adapters...")
        # Adapter 1: Camera events
        self.logger.info("Creating cam_events_adapter...")
        self.cam_events_adapter = JournalAdapterCamEvents()
        self.cam_events_adapter.set_params(**self.adapter_params.get('DatabaseAdapterCamEvents', {}))
        self.cam_events_adapter.init()
        self.logger.info("cam_events_adapter initialized")
        
        # Adapter 2: Perimeter events
        self.logger.info("Creating perimeter_events_adapter...")
        self.perimeter_events_adapter = JournalAdapterFieldOfViewEvents()
        self.perimeter_events_adapter.set_params(**self.adapter_params.get('DatabaseAdapterFieldOfViewEvents', {}))
        self.perimeter_events_adapter.init()
        self.logger.info("perimeter_events_adapter initialized")
        
        # Adapter 3: Zone events
        self.logger.info("Creating zone_events_adapter...")
        self.zone_events_adapter = JournalAdapterZoneEvents()
        self.zone_events_adapter.set_params(**self.adapter_params.get('DatabaseAdapterZoneEvents', {}))
        self.zone_events_adapter.init()
        self.logger.info("zone_events_adapter initialized")

        # Attribute events adapter (optional)
        try:
            self.logger.info("Creating attr_events_adapter...")
            from .journal_adapters.jadapter_attribute_events import JournalAdapterAttributeEvents
            self.attr_events_adapter = JournalAdapterAttributeEvents()
            if 'DatabaseAdapterAttributeEvents' in self.adapter_params:
                self.attr_events_adapter.set_params(**self.adapter_params['DatabaseAdapterAttributeEvents'])
            else:
                # fallback to same params as DB adapter
                self.attr_events_adapter.set_params(**{'table_name': 'attribute_events'})
            self.attr_events_adapter.init()
            self.logger.info("attr_events_adapter initialized")
        except Exception:
            self.attr_events_adapter = None
            self.logger.warning("attr_events_adapter creation failed, continuing without it")
        
        # System events (optional)
        try:
            self.logger.info("Initializing system events adapter...")
            self.system_events_adapter = JournalAdapterSystemEvents()
            if 'DatabaseAdapterSystemEvents' in self.adapter_params:
                self.system_events_adapter.set_params(**self.adapter_params['DatabaseAdapterSystemEvents'])
            else:
                self.system_events_adapter.set_params(**{'table_name': 'system_events'})
            self.system_events_adapter.init()
        except Exception:
            self.system_events_adapter = None
    
    def _create_journal_tabs(self):
        """Создать вкладки журналов лениво - только заглушки"""
        if not self.db_controller or not self.tables:
            return
            
        # Очищаем существующие вкладки
        while self.tabs.count() > 0:
            widget = self.tabs.widget(0)
            self.tabs.removeTab(0)
            if widget:
                widget.deleteLater()
        
        # Reset creation flags
        self._objects_journal_created = False
        self._events_journal_created = False
        
        # Set flag to prevent journal creation during initial setup
        self._initializing_tabs = True
        
        try:
            # Create placeholder tabs (journals will be created lazily on first switch)
            if self.obj_journal_enabled:
                # Add empty placeholder widget - journal will be created on first switch
                placeholder = QWidget()
                self.tabs.addTab(placeholder, 'Objects journal')
                self.logger.info("Objects journal placeholder tab added")
            
            # Add placeholder for events journal
            placeholder = QWidget()
            self.tabs.addTab(placeholder, 'Events journal')
            self.logger.info("Events journal placeholder tab added")
        finally:
            # Reset flag after tabs are created
            self._initializing_tabs = False
    
    def _on_tab_changed(self, index):
        """Обработчик переключения вкладок - создавать журналы лениво"""
        if index < 0 or not self.db_controller or not self.tables:
            return
        
        # Don't create journals during initial tab setup
        if self._initializing_tabs:
            return
        
        tab_text = self.tabs.tabText(index)
        widget = self.tabs.widget(index)
        
        # Get image directory from database params
        image_dir = self.db_params.get('image_dir', 'EvilEyeData')
        
        # Create Objects journal if needed
        if 'Objects' in tab_text and not self._objects_journal_created:
            self.logger.info("Lazy creating Objects journal...")
            
            # Set flag BEFORE operations to prevent recursion
            self._objects_journal_created = True
            
            try:
                # Create DatabaseJournalDataSource for objects
                objects_ds = DatabaseJournalDataSource(
                self.db_controller, 
                    journal_type='objects',
                    adapters=None,
                    database_params=self.database_params,
                    params=self.params,
                    image_dir=image_dir,
                    db_connection_name='unified_objects_conn'
                )
                
                # Create UnifiedObjectsJournal
                objects_journal = UnifiedObjectsJournal(
                    objects_ds,
                    base_dir=image_dir,
                    parent=self,
                    logger_name="unified_objects_journal",
                    parent_logger=self.logger
                )
                
                # Block signals during tab replacement to prevent currentChanged recursion
                self.tabs.blockSignals(True)
                try:
                    self.tabs.removeTab(index)
                    self.tabs.insertTab(index, objects_journal, 'Objects journal')
                    self.tabs.setCurrentIndex(index)
                finally:
                    self.tabs.blockSignals(False)
                
                self.logger.info("Objects journal created and added")
            except Exception as e:
                # Reset flag on error
                self._objects_journal_created = False
                self.logger.error(f"Failed to create UnifiedObjectsJournal: {e}")
                import traceback
                self.logger.error(f"Traceback: {traceback.format_exc()}")
        
        # Create Events journal if needed
        elif 'Events' in tab_text and not self._events_journal_created:
            self.logger.info("Lazy creating Events journal...")
            
            # Set flag BEFORE operations to prevent recursion
            self._events_journal_created = True
            
            try:
                # Prepare adapters for events journal
                adapters = [self.cam_events_adapter, self.perimeter_events_adapter, self.zone_events_adapter]
                if self.attr_events_adapter:
                    adapters.append(self.attr_events_adapter)
                if self.system_events_adapter:
                    adapters.append(self.system_events_adapter)
                
                # Create DatabaseJournalDataSource for events
                events_ds = DatabaseJournalDataSource(
                    self.db_controller,
                    journal_type='events',
                    adapters=adapters,
                    database_params=self.database_params,
                    params=self.params,
                    image_dir=image_dir,
                    db_connection_name='unified_events_conn'
                )
                
                # Create UnifiedEventsJournal
                events_journal_widget = UnifiedEventsJournal(
                    events_ds,
                    base_dir=image_dir,
                    parent=self,
                    logger_name="unified_events_journal",
                    parent_logger=self.logger
            )
                
                # Block signals during tab replacement to prevent currentChanged recursion
                self.tabs.blockSignals(True)
                try:
                    self.tabs.removeTab(index)
                    self.tabs.insertTab(index, events_journal_widget, 'Events journal')
                    self.tabs.setCurrentIndex(index)
                finally:
                    self.tabs.blockSignals(False)
                
                self.logger.info("Events journal created and added")
            except Exception as e:
                # Reset flag on error
                self._events_journal_created = False
                import traceback
                self.logger.error(f"Failed to create UnifiedEventsJournal: {e}")
                self.logger.error(f"Traceback: {traceback.format_exc()}")
    
    def _ensure_tab_initialized(self, index):
        """Ensure journal is initialized for the tab at given index"""
        if index < 0 or not self.db_controller or not self.tables:
            return
        
        # Check if journal already created
        tab_text = self.tabs.tabText(index)
        if 'Objects' in tab_text and self._objects_journal_created:
            return
        if 'Events' in tab_text and self._events_journal_created:
            return
        
        # Call _on_tab_changed to create journal
        self._on_tab_changed(index)

    def close(self):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            if tab:
                tab.close()
        self.logger.info('Database journal closed')
        
        # Only save and disconnect if database is available
        if hasattr(self, 'database_available') and self.database_available and self.db_controller and self.params:
            self.db_controller.save_job_configuration_info(self.params)
            self.db_controller.disconnect()

    def closeEvent(self, event):
        """Handle window close event"""
        self.logger.info("Database journal window close event")
        # Hide window instead of closing to keep it alive
        self.hide()
        event.accept()
        
        # Only close main window if configured to do so
        if self.main_window and self.close_app:
            self.main_window.close()

    @pyqtSlot(int)
    def _close_tab(self, idx):
        # Hide tab, keep widget and DB connection alive
        try:
            self.tabs.setTabVisible(idx, False)
        except Exception:
            pass
        # If all tabs are hidden, hide the whole journal window
        try:
            any_visible = False
            bar = self.tabs.tabBar()
            for i in range(self.tabs.count()):
                try:
                    if bar.isTabVisible(i):
                        any_visible = True
                        break
                except Exception:
                    # Fallback: if API not available, consider count>0 as visible
                    any_visible = self.tabs.count() > 0
                    break
            if not any_visible:
                self.hide()
        except Exception:
            pass

