from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QSizePolicy, QMenuBar, QToolBar, QDateTimeEdit, QHeaderView,
    QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem
)
from PyQt6.QtGui import QPixmap, QIcon
import sys
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from pathlib import Path
from database_controller import database_controller_pg
from visualization_modules import handler_journal_view
from visualization_modules import events_journal
from visualization_modules.journal_adapters.jadapter_fov_events import JournalAdapterFieldOfViewEvents
from visualization_modules.journal_adapters.jadapter_cam_events import JournalAdapterCamEvents
from visualization_modules.journal_adapters.jadapter_zone_events import JournalAdapterZoneEvents

sys.path.append(str(Path(__file__).parent.parent.parent))


class DatabaseJournalWindow(QWidget):
    def __init__(self, params):
        super().__init__()
        self.params = params
        self.adapter_params = self.params['database_adapters']
        self.db_params = self.params['database']
        self.vis_params = self.params['visualizer']
        self.obj_journal_enabled = self.vis_params['objects_journal_enabled']

        self.db_controller = database_controller_pg.DatabaseControllerPg(params, controller_type='Receiver')
        self.db_controller.set_params(**self.db_params)
        self.db_controller.init()
        self.db_controller.connect()
        self.tables = self.db_params['tables']

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
            self.tabs.addTab(handler_journal_view.HandlerJournal(self.db_controller, 'objects', self.params,
                                                                 self.tables['objects'], parent=self), 'Handler journal')
        self.tabs.addTab(events_journal.EventsJournal([self.cam_events_adapter,
                                                       self.perimeter_events_adapter, self.zone_events_adapter],
                                                      self.db_controller, 'objects', self.params,
                                                      self.tables['objects'], parent=self), 'Alarms journal')

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

    def close(self):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        print('Database journal closed')
        self.db_controller.disconnect()

    @pyqtSlot(int)
    def _close_tab(self, idx):
        tab = self.tabs.widget(idx)
        self.tabs.setTabVisible(idx, False)
        tab.close()

