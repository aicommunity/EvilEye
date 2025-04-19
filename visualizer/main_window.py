from PyQt6 import QtGui
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QMenuBar, QToolBar,
    QMenu, QMainWindow, QApplication
)

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QPixmap, QIcon
from PyQt6.QtGui import QAction
from PyQt6.QtCore import Qt
import sys
import cv2
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt
from pathlib import Path
from visualizer.video_thread import VideoThread
from controller import controller
from visualizer.db_journal import DatabaseJournalWindow
sys.path.append(str(Path(__file__).parent.parent.parent))


# Собственный класс для label, чтобы переопределить двойной клик мышкой
class MyLabel(QLabel):
    double_click_signal = pyqtSignal()

    def __init__(self):
        super(MyLabel, self).__init__()
        self.is_full = False

    def mouseDoubleClickEvent(self, event):
        super().mouseDoubleClickEvent(event)
        self.double_click_signal.emit()


class MainWindow(QMainWindow):
    def __init__(self, params, win_width, win_height):
        super().__init__()
        self.setWindowTitle("EvilEye")
        self.setMinimumSize(win_width, win_height)

        # self.handler = ObjectsHandler(self.num_labels, history_len=20)
        self.controller = controller.Controller(self, self.update_image)

        self.params = params
        self.rows = self.params['visualizer']['num_height']
        self.cols = self.params['visualizer']['num_width']
        self.sources = self.params['sources']
        self.num_sources = len(self.params['sources'])
        self.num_labels = 0
        self.labels = []
        self.threads = []
        self.hlayouts = []
        self.cameras = []

        self.setCentralWidget(QWidget())
        self._create_actions()
        self._connect_actions()
        self.menu_height = 0
        self._create_menu_bar()

        self.toolbar_width = 0
        self._create_toolbar()
        self.db_journal_win = DatabaseJournalWindow(self.params)
        self.db_journal_win.setVisible(False)

        for i in range(self.num_sources):
            if self.params['sources'][i]['split']:
                self.num_labels += self.params['sources'][i]['num_split']
            else:
                self.num_labels += 1
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
        for i in range(self.num_labels):
            self.labels.append(MyLabel())
            # Изменяем размер изображения по двойному клику
            self.labels[-1].double_click_signal.connect(self.change_screen_size)
            self.labels[-1].setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

            # Добавляем виджеты в layout в зависимости от начальных параметров (кол-во изображений по ширине и высоте)
            if grid_cols > self.cols - 1:
                grid_cols = 0
                grid_rows += 1
                if len(self.hlayouts) <= grid_rows:
                    print(f"grid_rows {grid_rows} > num horizontal layouts {len(self.hlayouts)}")
                else:
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
        self.menu_height = view_menu.frameGeometry().height()

    def _create_toolbar(self):
        view_toolbar = QToolBar('View', self)
        self.addToolBar(Qt.ToolBarArea.RightToolBarArea, view_toolbar)
        view_toolbar.addAction(self.db_journal)
        self.toolbar_width = view_toolbar.frameGeometry().width()

    def _create_actions(self):
        self.db_journal = QAction('&DB journal', self)
        self.db_journal.setIcon(QIcon('journal.svg'))

    def _connect_actions(self):
        self.db_journal.triggered.connect(self.open_journal)

    @pyqtSlot()
    def open_journal(self):
        if self.db_journal_win.isVisible():
            self.db_journal_win.setVisible(False)
        else:
            self.db_journal_win.setVisible(True)

    @pyqtSlot(int, QPixmap)
    def update_image(self, source_id: int, picture: QPixmap):
        # qt_image = self.convert_cv_qt(thread_data[0])
        # Обновляет label, в котором находится изображение
        self.labels[source_id].setPixmap(picture)

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
        self.controller.set_current_main_widget_size(self.geometry().width()-self.toolbar_width, self.geometry().height()-self.menu_height)

    def closeEvent(self, event):
        self.controller.release()
        self.db_journal_win.close()
        QApplication.closeAllWindows()
        event.accept()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:
        super().resizeEvent(event)
        self.controller.set_current_main_widget_size(self.geometry().width()-self.toolbar_width, self.geometry().height()-self.menu_height)

    def check_controller_status(self):
        if not self.controller.is_running():
            self.close()