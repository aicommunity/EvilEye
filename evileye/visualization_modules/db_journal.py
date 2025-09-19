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
from . import handler_journal_view
from . import events_journal
from .journal_adapters.jadapter_fov_events import JournalAdapterFieldOfViewEvents
from .journal_adapters.jadapter_cam_events import JournalAdapterCamEvents
from .journal_adapters.jadapter_zone_events import JournalAdapterZoneEvents

sys.path.append(str(Path(__file__).parent.parent.parent))


class DatabaseJournalWindow(QWidget):
    def __init__(self, main_window, params, database_params, close_app: bool):
        super().__init__()
        self.main_window = main_window
        self.params = params
        self.database_params = database_params
        
        # Handle case when database is disabled
        if not self.database_params or 'database_adapters' not in self.database_params:
            raise ValueError("Database journal cannot be created without database configuration")
            
        self.adapter_params = self.database_params['database_adapters']
        self.db_params = self.database_params['database']
        self.vis_params = self.params['visualizer']
        self.obj_journal_enabled = self.vis_params.get('objects_journal_enabled', True)

        self.db_controller = database_controller_pg.DatabaseControllerPg(params, controller_type='Receiver')
        self.db_controller.set_params(**self.db_params)
        self.db_controller.init()
        
        # Try to connect to database, fallback to no-database mode if connection fails
        try:
            self.db_controller.connect()
            self.tables = self.db_params['tables']
            self.database_available = True
        except Exception as e:
            print(f"Warning: Cannot connect to database. Database journal will be disabled. Reason: {e}")
            # Disable database functionality
            self.db_controller = None
            self.tables = {}
            # Set flag to indicate database is not available
            self.database_available = False

        self.cam_events_adapter = JournalAdapterCamEvents()
        self.cam_events_adapter.set_params(**self.adapter_params['DatabaseAdapterCamEvents'])
        self.cam_events_adapter.init()
        self.perimeter_events_adapter = JournalAdapterFieldOfViewEvents()
        self.perimeter_events_adapter.set_params(**self.adapter_params['DatabaseAdapterFieldOfViewEvents'])
        self.perimeter_events_adapter.init()
        self.zone_events_adapter = JournalAdapterZoneEvents()
        self.zone_events_adapter.set_params(**self.adapter_params['DatabaseAdapterZoneEvents'])
        self.zone_events_adapter.init()

        self.setWindowTitle('DB Journal')
        self.resize(1600, 600)

        self.tabs = QTabWidget()
        self.tabs.setTabsClosable(True)
        self.tabs.tabCloseRequested.connect(self._close_tab)
        if self.obj_journal_enabled:
            self.tabs.addTab(handler_journal_view.HandlerJournal(self.db_controller, 'objects', self.params, self.database_params,
                                                                 self.tables['objects'], parent=self), 'Objects journal')
        self.tabs.addTab(events_journal.EventsJournal([self.cam_events_adapter,
                                                       self.perimeter_events_adapter, self.zone_events_adapter],
                                                      self.db_controller, 'objects', self.params, self.database_params,
                                                      self.tables['objects'], parent=self), 'Events journal')

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

        self.close_app = close_app

    def close(self):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        print('Database journal closed')
        
        # Only save and disconnect if database is available
        if hasattr(self, 'database_available') and self.database_available and self.db_controller:
            self.db_controller.save_job_configuration_info(self.params)
            self.db_controller.disconnect()

    def closeEvent(self, event):
        if self.main_window and self.close_app:
            self.main_window.close()

    @pyqtSlot(int)
    def _close_tab(self, idx):
        tab = self.tabs.widget(idx)
        self.tabs.setTabVisible(idx, False)
        tab.close()

