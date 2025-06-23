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
import utils
import utils.utils
from visualization_modules.video_thread import VideoThread
from controller import controller
from visualization_modules.db_journal import DatabaseJournalWindow
from visualization_modules.zone_window import ZoneWindow
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

    def __init__(self, params_file_path, params, win_width, win_height):
        super().__init__()
        self.setWindowTitle("EvilEye")
        self.resize(win_width, win_height)
        self.slots = {'update_image': self.update_image, 'open_zone_win': self.open_zone_win}
        self.signals = {'display_zones_signal': self.display_zones_signal, 'add_zone_signal': self.add_zone_signal}

        self.controller = controller.Controller(self, self.slots, self.signals)

        self.params_path = params_file_path
        self.params = params
        self.rows = self.params['visualizer']['num_height']
        self.cols = self.params['visualizer']['num_width']
        self.cameras = self.params['sources']
        self.num_cameras = len(self.params['sources'])
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
        self.menu_height = 0
        self._create_menu_bar()

        self.toolbar_width = 0
        self._create_toolbar()
        self.db_journal_win = DatabaseJournalWindow(self.params)
        self.db_journal_win.setVisible(False)
        self.zone_window = ZoneWindow(self.params)
        self.zone_window.setVisible(False)

        vertical_layout = QVBoxLayout()
        for i in range(self.rows):
            self.hlayouts.append(QHBoxLayout())
            vertical_layout.addLayout(self.hlayouts[-1])
        self.centralWidget().setLayout(vertical_layout)
        self.setup_layout()

        self.controller.init(self.params)
        self.controller.start()

        self.timer = QTimer()
        self.timer.timeout.connect(self.check_controller_status)
        self.timer.setInterval(1000)
        self.timer.start()

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
        icon_path = os.path.join(utils.utils.get_project_root(), 'journal.svg')
        self.db_journal.setIcon(QIcon(icon_path))

        self.add_zone = QAction('&Add zone', self)
        icon_path = os.path.join(utils.utils.get_project_root(), 'add_zone.svg')
        self.add_zone.setIcon(QIcon(icon_path))
        self.show_zones = QAction('&Display zones', self)
        icon_path = os.path.join(utils.utils.get_project_root(), 'display_zones.svg')
        self.show_zones.setIcon(QIcon(icon_path))
        self.show_zones.setCheckable(True)

    def _connect_actions(self):
        self.db_journal.triggered.connect(self.open_journal)
        self.add_zone.triggered.connect(self.select_source)
        self.show_zones.toggled.connect(self.display_zones)

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
        self.controller.release()
        self.zone_window.close()
        self.db_journal_win.close()
        with open(self.params_path, 'w') as params_file:
            json.dump(self.params, params_file, indent=4)
        QApplication.closeAllWindows()
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.controller.set_current_main_widget_size(self.geometry().width()-self.toolbar_width, self.geometry().height()-self.menu_height)

    def check_controller_status(self):
        if not self.controller.is_running():
            self.close()
