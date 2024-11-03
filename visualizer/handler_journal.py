import datetime
import os
from psycopg2 import sql
from utils import event
from utils import utils
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QSizePolicy, QDateTimeEdit, QHeaderView,
    QTableWidget, QTableWidgetItem
)
from PyQt6.QtGui import QPixmap
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt


class HandlerJournal(QWidget):
    def __init__(self, db_controller, table_name, params, table_params, parent=None):
        super().__init__(parent)
        self.db_controller = db_controller

        self.params = params
        self.db_params = (self.params['user_name'], self.params['password'], self.params['database_name'],
                          self.params['host_name'], self.params['port'])
        self.username, self.password, self.db_name, self.host, self.port = self.db_params
        self.db_table_params = table_params
        self.table_name = table_name

        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False

        self._setup_table()
        self._setup_time_layout()

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.time_layout)
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self._retrieve_data()
        event.subscribe('handler new object', self._update_db)
        event.subscribe('handler fields updated', self._update_on_lost)

    def _setup_table(self):
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Message type', 'Time', 'Time lost',
                                              'Information', 'Preview', 'Preview lost'])
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(3).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(4).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(5).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)

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
        self.start_time.setCalendarPopup(True)
        self.start_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.start_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.start_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.start_time.setKeyboardTracking(False)
        self.start_time.dateTimeChanged.connect(self.start_time_update)

        self.finish_time = QDateTimeEdit()
        self.finish_time.setCalendarPopup(True)
        self.finish_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.finish_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.finish_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.finish_time.setKeyboardTracking(False)
        self.finish_time.dateTimeChanged.connect(self.finish_time_update)

    def _setup_buttons(self):
        self.reset_button = QPushButton('Reset')
        self.reset_button.clicked.connect(self._reset_filter)
        self.search_button = QPushButton('Search')
        self.search_button.clicked.connect(self._filter_by_time)

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
            self.table.setRowCount(0)
            self._retrieve_data()
            self.block_updates = False

    @pyqtSlot()
    def _filter_by_time(self):
        if not self.start_time_updated or not self.finish_time_updated:
            return
        self._filter_records(self.start_time.dateTime(), self.finish_time.dateTime())

    def _filter_records(self, start_time, finish_time):
        fields = self.db_table_params.keys()
        query = sql.SQL('SELECT count, {fields} FROM {table} WHERE time_stamp BETWEEN %s AND %s;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        data = (start_time.toPyDateTime(), finish_time.toPyDateTime())
        records = self.db_controller.query(query, data)
        self.table.setRowCount(0)
        self._append_rows(records)
        self.start_time_updated = False
        self.finish_time_updated = False

    def _retrieve_data(self):
        fields = self.db_table_params.keys()
        query = sql.SQL('SELECT count, {fields} FROM {table} WHERE time_stamp BETWEEN %s AND %s;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        data = (start_time, end_time)
        records = self.db_controller.query(query, data)
        self._append_rows(records)

    def _update_db(self):
        if self.block_updates:
            return
        fields = self.db_table_params.keys()
        query = sql.SQL('SELECT count, {fields} FROM {table} WHERE count=(SELECT MAX(count) FROM {table});').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        records = self.db_controller.query(query)
        self._append_rows(records)

    def _update_on_lost(self, fields_list, data):
        record = data[0]
        row_idx = record[0]
        print(row_idx)
        root = utils.get_project_root()
        lost_img_idx = fields_list.index('lost_preview_path') + 1
        time_lost_idx = fields_list.index('time_lost') + 1
        print(record[lost_img_idx])
        lost_pixmap = QPixmap(os.path.join(root, record[lost_img_idx]))
        lost_img = QTableWidgetItem()
        lost_img.setData(Qt.DecorationRole, lost_pixmap)
        self.table.setItem(row_idx - 1, 5, lost_img)
        self.table.setItem(row_idx - 1, 2, QTableWidgetItem(record[time_lost_idx].strftime('%H:%M:%S %d/%m/%Y')))

    def _append_rows(self, records):
        info_str = 'Event'
        fields = list(self.db_table_params.keys())
        id_idx = fields.index('object_id') + 1
        bbox_idx = fields.index('bounding_box') + 1
        conf_idx = fields.index('confidence') + 1
        class_idx = fields.index('class_id') + 1
        time_idx = fields.index('time_stamp') + 1
        time_lost_idx = fields.index('time_lost') + 1
        img_path_idx = fields.index('preview_path') + 1
        lost_img_idx = fields.index('lost_preview_path') + 1
        root = utils.get_project_root()
        for record in records:
            pixmap = QPixmap(os.path.join(root, record[img_path_idx]))
            preview_img = QTableWidgetItem()
            preview_img.setData(Qt.DecorationRole, pixmap)
            lost_pixmap = QPixmap()
            if record[lost_img_idx]:
                lost_pixmap.load(os.path.join(root, record[lost_img_idx]))
            lost_img = QTableWidgetItem()
            lost_img.setData(Qt.DecorationRole, lost_pixmap)
            row = self.table.rowCount()
            self.table.insertRow(row)
            res_str = ('Object ' + str(record[id_idx]) + ' emerged at [' +
                       str(record[bbox_idx]) + '], Conf: ' +
                       str(record[conf_idx]) + ', Class: ' + str(record[class_idx]))
            self.table.setItem(row, 0, QTableWidgetItem(info_str))
            self.table.setItem(row, 1, QTableWidgetItem(record[time_idx].strftime('%H:%M:%S %d/%m/%Y')))
            if record[time_lost_idx]:
                self.table.setItem(row, 2, QTableWidgetItem(record[time_lost_idx].strftime('%H:%M:%S %d/%m/%Y')))
            else:
                self.table.setItem(row, 2, QTableWidgetItem(record[time_lost_idx]))
            self.table.setItem(row, 3, QTableWidgetItem(res_str))
            self.table.setItem(row, 4, preview_img)
            self.table.setItem(row, 5, lost_img)
        self.table.resizeRowsToContents()
