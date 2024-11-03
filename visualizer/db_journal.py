from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QSizePolicy, QMenuBar, QToolBar, QAction, QDateTimeEdit, QHeaderView,
    QMenu, QMainWindow, QMessageBox, QTableView, QTableWidget, QTableWidgetItem
)
from PyQt5.QtGui import QPixmap, QIcon
import sys
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
from pathlib import Path
from database_controller import database_controller_pg
from visualizer import handler_journal
sys.path.append(str(Path(__file__).parent.parent.parent))


class DatabaseJournalWindow(QWidget):
    def __init__(self, db_params):
        super().__init__()
        self.params = db_params
        self.db_controller = database_controller_pg.DatabaseControllerPg()
        self.db_controller.init()
        self.db_controller.set_params(**self.params)
        self.db_controller.connect()
        self.tables = self.params['tables']
        self.setWindowTitle('DB Journal')
        self.resize(900, 600)

        self.tabs = QTabWidget()
        self.tabs.addTab(handler_journal.HandlerJournal(self.db_controller, 'emerged', self.params, self.tables['emerged']), 'Handler journal')
        self.tabs.addTab(QWidget(), 'Alarms journal')

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.tabs)
        self.setLayout(self.layout)

    def closeEvent(self, event):
        self.db_controller.disconnect()
