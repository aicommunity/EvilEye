import json

try:
    from PyQt6 import QtGui
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout,
        QSizePolicy, QMenuBar, QToolBar,
        QMenu, QMainWindow, QApplication
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
        QMenu, QMainWindow, QApplication
    )

    from PyQt5.QtCore import QTimer
    from PyQt5.QtGui import QPixmap, QIcon, QCursor
    from PyQt5.QtWidgets import QAction
    from PyQt5.QtCore import Qt
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
    pyqt_version = 5

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
sys.path.append(str(Path(__file__).parent.parent.parent))


# Собственный класс для label, чтобы переопределить двойной клик мышкой
class DoubleClickLabel(QLabel):
    double_click_signal = pyqtSignal()
    add_zone_signal = pyqtSignal()
    is_add_zone_clicked = False

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
        event.accept()

    def add_zone_clicked(self, flag):  # Для изменения курсора в момент выбора источника
        DoubleClickLabel.is_add_zone_clicked = flag
        if flag:
            self.setCursor(QCursor(Qt.CursorShape.PointingHandCursor))
        else:
            self.setCursor(QCursor(Qt.CursorShape.ArrowCursor))

    def ready_to_display(self, flag):
        self.is_ready_to_display = flag


class MainWindow(QMainWindow):
    display_zones_signal = pyqtSignal(dict)
    add_zone_signal = pyqtSignal(int)

    def __init__(self, controller, params_file_path, params, win_width, win_height):
        super().__init__()
        self.setWindowTitle("EvilEye")
        self.resize(win_width, win_height)
        self.slots = {'update_image': self.update_image, 'open_zone_win': self.open_zone_win}
        self.signals = {'display_zones_signal': self.display_zones_signal, 'add_zone_signal': self.add_zone_signal}

        self.controller = controller

        self.params_path = params_file_path
        self.params = params

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

        self.setCentralWidget(QWidget())
        self._create_actions()
        self._connect_actions()

        close_app = False
        if self.controller.enable_close_from_gui and not self.controller.show_main_gui and self.controller.show_journal:
            close_app = True

        # Create journal window (DB or JSON mode)
        if hasattr(self.controller, 'use_database') and self.controller.use_database:
            try:
                self.db_journal_win = DatabaseJournalWindow(self, self.params, self.controller.database_config, close_app)
                self.db_journal_win.setVisible(False)
            except Exception as e:
                print(f"Warning: Failed to create database journal window. Falling back to JSON mode. Reason: {e}")
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
                    self.db_journal_win = EventsJournalJson(images_dir)
                    self.db_journal_win.setVisible(False)
                except Exception as e:
                    print(f"Error creating JSON journal: {e}")
                    self.db_journal_win = None
            else:
                print(f"Images directory does not exist: {images_dir}")
                self.db_journal_win = None
        self.zone_window = ZoneWindow(self.params)
        self.zone_window.setVisible(False)

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

            # Добавляем виджеты в layout в зависимости от начальных параметров (кол-во изображений по ширине и высоте)
            if grid_cols > self.cols - 1:
                grid_cols = 0
                grid_rows += 1
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignmentFlag.AlignCenter)
                grid_cols += 1
            else:
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignmentFlag.AlignCenter)
                grid_cols += 1

    def _create_menu_bar(self):
        menu = self.menuBar()

        view_menu = QMenu('&View', self)
        menu.addMenu(view_menu)
        view_menu.addAction(self.db_journal)
        view_menu.addAction(self.show_zones)
        self.menu_height = view_menu.frameGeometry().height()

        edit_menu = QMenu('&Edit', self)
        menu.addMenu(edit_menu)
        edit_menu.addAction(self.add_zone)

        #configure_menu = QMenu('&Configure', self)
        #menu.addMenu(configure_menu)
        #configure_menu.addAction(self.add_channel)
        #configure_menu.addAction(self.del_channel)

    def _create_toolbar(self):
        view_toolbar = QToolBar('View', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, view_toolbar)
        view_toolbar.addAction(self.db_journal)
        self.toolbar_width = view_toolbar.frameGeometry().width()

        edit_toolbar = QToolBar('Edit', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, edit_toolbar)
        edit_toolbar.addAction(self.add_zone)
        edit_toolbar.addAction(self.show_zones)
        self.toolbar_width = edit_toolbar.frameGeometry().width()

    def _create_actions(self):  # Создание кнопок-действий
        self.db_journal = QAction('&DB journal', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'journal.svg')
        self.db_journal.setIcon(QIcon(icon_path))
        # Journal button configuration will be done after journal window creation

        self.add_zone = QAction('&Add zone', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'add_zone.svg')
        self.add_zone.setIcon(QIcon(icon_path))
        self.show_zones = QAction('&Display zones', self)
        icon_path = os.path.join(utils_utils.get_project_root(), 'icons', 'display_zones.svg')
        self.show_zones.setIcon(QIcon(icon_path))
        self.show_zones.setCheckable(True)

        self.add_channel = QAction('&Add Channel', self)
        self.del_channel = QAction('&Del Channel', self)

    def _connect_actions(self):
        self.db_journal.triggered.connect(self.open_journal)
        self.add_zone.triggered.connect(self.select_source)
        self.show_zones.toggled.connect(self.display_zones)
        self.add_channel.triggered.connect(self.add_channel_slot)
        self.del_channel.triggered.connect(self.del_channel_slot)

    def _configure_journal_button(self):
        """Configure journal button based on database mode and availability"""
        if hasattr(self.controller, 'use_database') and self.controller.use_database:
            # Database mode - use original DB journal
            self.db_journal.setEnabled(True)
            self.db_journal.setText('&DB journal')
            self.db_journal.setToolTip("Open database events journal")
        else:
            # JSON mode - check if journal was created successfully
            if self.db_journal_win is not None:
                self.db_journal.setEnabled(True)
                self.db_journal.setText('&Journal')
                self.db_journal.setToolTip("Open events journal (JSON mode)")
            else:
                # Disable button if no journal is available (directory doesn't exist or creation failed)
                self.db_journal.setEnabled(False)
                self.db_journal.setText('&Journal')
                self.db_journal.setToolTip("Journal is not available (images directory not found)")

    @pyqtSlot()
    def display_zones(self):  # Включение отображения зон
        if self.show_zones.isChecked():
            zones = self.zone_window.get_zone_info()
            self.display_zones_signal.emit(zones)
        else:
            self.display_zones_signal.emit({})

    @pyqtSlot()
    def select_source(self):  # Выбор источника для добавления зон
        if self.show_zones.isChecked():
            self.show_zones.setChecked(False)
        for label in self.labels:
            label.add_zone_clicked(True)

    @pyqtSlot()
    def open_journal(self):
        if self.db_journal_win is None:
            print("Journal is not available (database disabled or initialization failed)")
            return
        if self.db_journal_win.isVisible():
            self.db_journal_win.setVisible(False)
        else:
            self.db_journal_win.setVisible(True)

    @pyqtSlot(int, QPixmap)
    def open_zone_win(self, label_id: int, pixmap: QPixmap):
        if self.zone_window.isVisible():
            self.zone_window.setVisible(False)
        else:
            self.zone_window.setVisible(True)
            self.zone_window.set_pixmap(self.labels_sources_ids[label_id], pixmap)  # Перенос изображения от выбранного источника в окно выбора зон
        for label in self.labels:
            label.add_zone_clicked(False)

    @pyqtSlot(int, QPixmap)
    def update_image(self, label_id: int, picture: QPixmap):
        # Обновляет label, в котором находится изображение
        self.labels[label_id].setPixmap(picture)

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
        self.add_zone_signal.emit(label_id)

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
                self.db_journal_win = EventsJournalJson(images_dir)
                self.db_journal_win.setVisible(False)
            except Exception as e:
                print(f"Error creating JSON journal: {e}")
                self.db_journal_win = None
        else:
            print(f"Images directory does not exist: {images_dir}")
            self.db_journal_win = None

    @pyqtSlot()
    def del_channel_slot(self):  # Выбор источника для добавления зон
        pass