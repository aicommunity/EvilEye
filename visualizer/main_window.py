from PyQt5 import QtGui
from PyQt5.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout,
    QSizePolicy, QMenuBar, QToolBar, QAction,
    QMenu, QMainWindow, QApplication
)
from PyQt5.QtGui import QPixmap, QIcon
import sys
import cv2
from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt
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
        self.controller = controller.Controller(self.update_image)

        self.params = params
        self.rows = self.params['visualizer']['num_height']
        self.cols = self.params['visualizer']['num_width']
        self.db_params = self.params['database']
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
        self._create_menu_bar()
        self._create_toolbar()
        self.db_journal_win = DatabaseJournalWindow(self.db_params)

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

    def setup_layout(self):
        self.centralWidget().layout().setContentsMargins(0, 0, 0, 0)
        grid_cols = 0
        grid_rows = 0
        for i in range(self.num_labels):
            self.labels.append(MyLabel())
            # Изменяем размер изображения по двойному клику
            self.labels[-1].double_click_signal.connect(self.change_screen_size)
            self.labels[-1].setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Ignored)

            # Добавляем виджеты в layout в зависимости от начальных параметров (кол-во изображений по ширине и высоте)
            if grid_cols > self.cols - 1:
                grid_cols = 0
                grid_rows += 1
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignCenter)
                grid_cols += 1
            else:
                self.hlayouts[grid_rows].addWidget(self.labels[-1], alignment=Qt.AlignCenter)
                grid_cols += 1

    def _create_menu_bar(self):
        menu = self.menuBar()

        view_menu = QMenu('&View', self)
        menu.addMenu(view_menu)
        view_menu.addAction(self.db_journal)

    def _create_toolbar(self):
        view_toolbar = QToolBar('View', self)
        self.addToolBar(Qt.RightToolBarArea, view_toolbar)
        view_toolbar.addAction(self.db_journal)

    def _create_actions(self):
        self.db_journal = QAction('&DB journal', self)
        self.db_journal.setIcon(QIcon('journal.svg'))

    def _connect_actions(self):
        self.db_journal.triggered.connect(self.open_journal)

    def convert_cv_qt(self, cv_img):
        # Переводим из opencv image в QPixmap
        rgb_image = cv2.cvtColor(cv_img, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb_image.shape
        bytes_per_line = ch * w
        convert_to_qt = QtGui.QImage(rgb_image.data, w, h, bytes_per_line, QtGui.QImage.Format_RGB888)
        # Подгоняем под указанный размер, но сохраняем пропорции
        scaled_image = convert_to_qt.scaled(int(self.geometry().width() / VideoThread.cols),
                                            int(self.geometry().height() / VideoThread.rows), Qt.KeepAspectRatio)
        return QPixmap.fromImage(scaled_image)

    @pyqtSlot()
    def open_journal(self):
        if self.db_journal_win.isVisible():
            self.db_journal_win.hide()
        else:
            self.db_journal_win.show()

    @pyqtSlot(list)
    def update_image(self, thread_data):
        qt_image = self.convert_cv_qt(thread_data[0])
        # Обновляет label, в котором находится изображение
        self.labels[thread_data[1]].setPixmap(qt_image)

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

    def closeEvent(self, event):
        self.controller.stop()
        QApplication.closeAllWindows()
        event.accept()
