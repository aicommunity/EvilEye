import datetime
import json
try:
    from PyQt6.QtCore import QDate, QDateTime
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QLineEdit, QTableView, QStyledItemDelegate,
        QMessageBox, QTextEdit, QFormLayout, QSizePolicy
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QDate, QDateTime
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QLineEdit, QTableView, QStyledItemDelegate,
        QMessageBox, QTextEdit, QFormLayout, QSizePolicy
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5
from . import parameters_processing


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        return value.toString(Qt.DateFormat.ISODate)


class ParamsWindow(QWidget):
    def __init__(self):
        super().__init__(parent=None)
        self.setWindowTitle('Parameters')
        self.setFixedSize(900, 600)
        self.image_path = None
        self.text = QTextEdit()
        self.save_button = QPushButton('Save parameters', self)
        self.save_button.clicked.connect(self._save_data)
        self.file_name = QLabel('Enter file name')
        self.file_name_edit = QTextEdit()
        self.file_name_edit.setText('.json')
        self.file_name_edit.setFixedHeight(self.save_button.geometry().height())
        self.h_layout = QHBoxLayout()
        self.h_layout.addWidget(self.file_name)
        self.h_layout.addWidget(self.file_name_edit)
        self.h_layout.addWidget(self.save_button)

        self.layout = QVBoxLayout()
        self.layout.addWidget(self.text)
        self.layout.addLayout(self.h_layout)
        self.setLayout(self.layout)
        self.setVisible(False)

    def set_data(self, json_dict):
        editable_json = json.dumps(json_dict, indent=4)
        self.text.setText(editable_json)
        self.setVisible(True)

    @pyqtSlot()
    def _save_data(self):
        file_name = self.file_name_edit.toPlainText()
        if not file_name.strip('.json'):
            file_name = 'temp.json'
        json_str = self.text.toPlainText()
        json_dict = json.loads(json_str)
        with open(file_name, 'w') as file:
            json.dump(json_dict, file, indent=4)
        self.close()


class JobsHistory(QWidget):
    retrieve_data_signal = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__()
        self.setMinimumSize(1280, 720)

        self.last_row_db = 0
        self.data_for_update = []
        self.last_update_time = None
        self.update_rate = 10
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False
        self.params_win = ParamsWindow()

        self._setup_table()
        self._setup_time_layout()
        self.filter_displayed = False

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.time_layout)
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self.retrieve_data_signal.connect(self._retrieve_data)
        self.table.doubleClicked.connect(self._display_params)

    def _setup_table(self):
        self._setup_model()

        self.table = QTableView()
        self.table.setModel(self.model)
        header = self.table.verticalHeader()
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)

        self.date_delegate = DateTimeDelegate(None)
        self.table.setItemDelegateForColumn(3, self.date_delegate)

    def _setup_model(self):
        self.model = QSqlQueryModel()

        query = QSqlQuery(QSqlDatabase.database('jobs_conn'))
        query.prepare('SELECT first.project_id, first.job_id, first.configuration_id, first.creation_time, '
                      ' second.configuration_info FROM'
                      ' (SELECT project_id, job_id, configuration_id, creation_time FROM jobs) AS first INNER JOIN'
                      ' (SELECT configuration_id, configuration_info FROM jobs WHERE configuration_info is NOT NULL)'
                      ' AS second ON first.configuration_id = second.configuration_id'
                      ' WHERE creation_time BETWEEN :start AND :finish ORDER BY creation_time DESC;')
        # query.prepare('SELECT project_id, job_id, configuration_id, configuration_info, creation_time FROM jobs '
        #               'WHERE creation_time BETWEEN :start AND :finish ORDER BY creation_time DESC')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()

        self.model.setQuery(query)
        self.model.setHeaderData(0, Qt.Orientation.Horizontal, self.tr('Project ID'))
        self.model.setHeaderData(1, Qt.Orientation.Horizontal, self.tr('Job ID'))
        self.model.setHeaderData(2, Qt.Orientation.Horizontal, self.tr('Configuration ID'))
        self.model.setHeaderData(3, Qt.Orientation.Horizontal, self.tr('Time'))
        self.model.setHeaderData(4, Qt.Orientation.Horizontal, self.tr('Configuration JSON'))

    def _setup_time_layout(self):
        self._setup_datetime()
        self._setup_buttons()

        self.time_layout = QHBoxLayout()
        self.time_layout.addWidget(self.start_time)
        self.time_layout.addWidget(self.finish_time)
        self.time_layout.addWidget(self.reset_button)
        self.time_layout.addWidget(self.search_button)

    def _setup_datetime(self):
        self.start_time = QDateTimeEdit()
        self.start_time.setMinimumWidth(200)
        self.start_time.setCalendarPopup(True)
        self.start_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.start_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.start_time.setDateTime(self.current_start_time)
        self.start_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.start_time.setKeyboardTracking(False)
        self.start_time.editingFinished.connect(self.start_time_update)

        self.finish_time = QDateTimeEdit()
        self.finish_time.setMinimumWidth(200)
        self.finish_time.setCalendarPopup(True)
        self.finish_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.finish_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.finish_time.setDateTime(self.current_end_time)
        self.finish_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.finish_time.setKeyboardTracking(False)
        self.finish_time.editingFinished.connect(self.finish_time_update)

    def _setup_buttons(self):
        self.reset_button = QPushButton('Reset')
        self.reset_button.setMinimumWidth(200)
        self.reset_button.clicked.connect(self._reset_filter)
        self.search_button = QPushButton('Search')
        self.search_button.setMinimumWidth(200)
        self.search_button.clicked.connect(self._filter_by_time)

    def showEvent(self, show_event):
        self.retrieve_data_signal.emit()
        show_event.accept()

    @pyqtSlot()
    def start_time_update(self):
        self.block_updates = True
        if self.start_time.calendarWidget().hasFocus():
            return
        self.start_time_updated = True

    @pyqtSlot()
    def finish_time_update(self):
        self.block_updates = True
        if self.finish_time.calendarWidget().hasFocus():
            return
        self.finish_time_updated = True

    @pyqtSlot()
    def _reset_filter(self):
        if self.block_updates:
            self._retrieve_data()
            self.block_updates = False

    @pyqtSlot()
    def _filter_by_time(self):
        if not self.start_time_updated or not self.finish_time_updated:
            return
        self._filter_records(self.start_time.dateTime().toPyDateTime(), self.finish_time.dateTime().toPyDateTime())

    def _filter_records(self, start_time, finish_time):
        self.current_start_time = start_time
        self.current_end_time = finish_time
        query = QSqlQuery(QSqlDatabase.database('jobs_conn'))
        query.prepare('SELECT first.project_id, first.job_id, first.configuration_id, first.creation_time, '
                      ' second.configuration_info FROM'
                      ' (SELECT project_id, job_id, configuration_id, creation_time FROM jobs) AS first INNER JOIN'
                      ' (SELECT configuration_id, configuration_info FROM jobs WHERE configuration_info is NOT NULL)'
                      ' AS second ON first.configuration_id = second.configuration_id'
                      ' WHERE creation_time BETWEEN :start AND :finish ORDER BY creation_time DESC;')
        query.bindValue(":start", start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", finish_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    def _retrieve_data(self):
        if not self.isVisible():
            return

        query = QSqlQuery(QSqlDatabase.database('jobs_conn'))
        query.prepare('SELECT first.project_id, first.job_id, first.configuration_id, first.creation_time, '
                      ' second.configuration_info FROM'
                      ' (SELECT project_id, job_id, configuration_id, creation_time FROM jobs) AS first INNER JOIN'
                      ' (SELECT configuration_id, configuration_info FROM jobs WHERE configuration_info is NOT NULL)'
                      ' AS second ON first.configuration_id = second.configuration_id'
                      ' WHERE creation_time BETWEEN :start AND :finish ORDER BY creation_time DESC;')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        # Сбрасываем дату в фильтрах
        self.start_time.setDateTime(
            QDateTime.fromString(self.current_start_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))
        self.finish_time.setDateTime(
            QDateTime.fromString(self.current_end_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))

        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    @pyqtSlot(QModelIndex)
    def _display_params(self, index):
        col = index.column()
        if col != 4:
            return
        json_string = index.data()
        json_dict = json.loads(json_string)
        self.params_win.set_data(json_dict)
