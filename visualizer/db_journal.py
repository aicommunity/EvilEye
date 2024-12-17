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
from visualizer import handler_journal_view
from visualizer import handler_journal

sys.path.append(str(Path(__file__).parent.parent.parent))


class DatabaseJournalWindow(QWidget):
    def __init__(self, params):
        super().__init__()
        self.params = params
        self.db_params = self.params['database']
        self.db_controller = database_controller_pg.DatabaseControllerPg(params, controller_type='Receiver')
        self.db_controller.set_params(**self.db_params)
        self.db_controller.init()
        self.db_controller.connect()
        self.tables = self.db_params['tables']
        self.setWindowTitle('DB Journal')
        self.resize(900, 600)

        self.tabs = QTabWidget()
        self.tabs.addTab(handler_journal_view.HandlerJournal(self.db_controller, 'objects', self.params,
                                                             self.tables['objects'], parent=self), 'Handler journal')
        self.tabs.addTab(QWidget(), 'Alarms journal')

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

    def close(self):
        for tab_idx in range(self.tabs.count()):
            tab = self.tabs.widget(tab_idx)
            tab.close()
        print('Database journal closed')
        self.db_controller.disconnect()
