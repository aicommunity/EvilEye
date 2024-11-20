import datetime
import os
from psycopg2 import sql
from utils import event
from utils import utils
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QSizePolicy, QDateTimeEdit, QHeaderView,
    QTableWidget, QTableWidgetItem, QApplication, QAbstractItemView
)
from PyQt6.QtGui import QPixmap, QPainter, QPen
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer
from visualizer.table_updater import TableUpdater


class HandlerJournal(QWidget):
    retrieve_data_signal = pyqtSignal()

    preview_width = 300
    preview_height = 150

    def __init__(self, db_controller, table_name, params, table_params, parent=None):
        super().__init__(parent)
        self.db_controller = db_controller
        self.table_updater = TableUpdater(table_name, self._update_db, self.db_controller)

        self.params = params
        self.db_params = (self.params['user_name'], self.params['password'], self.params['database_name'],
                          self.params['host_name'], self.params['port'], self.params['image_dir'])
        self.username, self.password, self.db_name, self.host, self.port, self.image_dir = self.db_params
        self.db_table_params = table_params
        self.table_name = table_name

        self.table_data_thread = None

        self.last_row_db = 0
        self.data_for_update = []
        self.last_update_time = None
        self.update_rate = 10
        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False

        self._setup_table()
        self._setup_time_layout()

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.time_layout)
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self.retrieve_data_signal.connect(self._retrieve_data)
        self.table_updater.set_params(**table_params)
        self.table_updater.init()
        self.table_updater.start()

    def _setup_table(self):
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(['Message type', 'Time', 'Information', 'Preview'])
        self.table.horizontalHeaderItem(0).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(1).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeaderItem(2).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeaderItem(3).setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(HandlerJournal.preview_height)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)

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

    def showEvent(self, show_event):
        # print('SHOW EVENT CALLED')
        self.last_update_time = datetime.datetime.now()
        self.table.setRowCount(0)
        self.last_row_db = 0
        self.retrieve_data_signal.emit()
        show_event.accept()

    @pyqtSlot()
    def _notify_db_update(self):
        event.notify('handler new object')

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
            self.last_row_db = 0
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
        self.setUpdatesEnabled(False)
        # self.blockSignals(True)
        self._append_rows(records)
        self.setUpdatesEnabled(True)
        # self.blockSignals(False)
        self.start_time_updated = False
        self.finish_time_updated = False
        QApplication.processEvents()

    def _retrieve_data(self):
        if not self.isVisible():
            return
        fields = self.db_table_params.keys()
        query = sql.SQL(
            'SELECT count, {fields} FROM {table} WHERE time_stamp BETWEEN %s AND %s ORDER BY count;').format(
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(self.table_name))
        start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        data = (start_time, end_time)
        records = self.db_controller.query(query, data)
        self._append_rows(records)

    @pyqtSlot(list)
    def _update_db(self, records):
        if self.block_updates or not self.isVisible():
            return

        self.table.setUpdatesEnabled(False)
        # self.table.blockSignals(True)
        self._append_rows(records)
        self.table.setUpdatesEnabled(True)
        # self.table.blockSignals(False)
        QApplication.processEvents()

    def _update_on_lost(self, fields_list, data):
        if not self.isVisible():
            print('HIDDEN')
            return

        record = data[0]
        cur_update_time = datetime.datetime.now()
        if (cur_update_time - self.last_update_time).total_seconds() < self.update_rate:
            self.data_for_update.append(record)
            return
        self.last_update_time = cur_update_time
        self.data_for_update.append(record)

        for rec in self.data_for_update:
            row_idx = rec[0]
            #print(row_idx)
            root = utils.get_project_root()
            lost_img_idx = fields_list.index('lost_preview_path') + 1
            time_lost_idx = fields_list.index('time_lost') + 1
            #print(rec[lost_img_idx])
            lost_pixmap = QPixmap(os.path.join(root, rec[lost_img_idx]))
            lost_img = QTableWidgetItem()
            lost_img.setData(Qt.ItemDataRole.DecorationRole, lost_pixmap)
            self.table.setUpdatesEnabled(False)
            self.table.blockSignals(True)
            self.table.setItem(row_idx - 1, 4, lost_img)
            self.table.setItem(row_idx - 1, 2, QTableWidgetItem(rec[time_lost_idx].strftime('%H:%M:%S %d/%m/%Y')))
            self.table.setUpdatesEnabled(True)
            self.table.blockSignals(False)
            QApplication.processEvents()

    def _append_rows(self, records):
        info_str = 'Event'
        fields = list(self.db_table_params.keys())
        count_idx = 0
        id_idx = fields.index('object_id') + 1
        bbox_idx = fields.index('bounding_box') + 1
        conf_idx = fields.index('confidence') + 1
        class_idx = fields.index('class_id') + 1
        time_idx = fields.index('time_stamp') + 1
        time_lost_idx = fields.index('time_lost') + 1
        img_path_idx = fields.index('preview_path') + 1
        lost_img_idx = fields.index('lost_preview_path') + 1
        root = self.image_dir

        if records is None:
            return

        last_row = self.last_row_db
        for record in records:
            if record[count_idx] <= last_row:
                continue
            rect = record[bbox_idx]
            pixmap = QPixmap(os.path.join(root, record[img_path_idx]))
            qp = QPainter(pixmap)
            pen = QPen(Qt.GlobalColor.green, 1)
            qp.setPen(pen)
            qp.drawRect(int(rect[0]*HandlerJournal.preview_width), int(rect[1]*HandlerJournal.preview_height),
                        int((rect[2]-rect[0])*HandlerJournal.preview_width), int((rect[3]-rect[1])*HandlerJournal.preview_height))
            qp.end()

#            cv2.rectangle(image.image, (int(last_info.bounding_box[0]), int(last_info.bounding_box[1])),
#                          (int(last_info.bounding_box[2]), int(last_info.bounding_box[3])), (0, 255, 0), thickness=8)
#            cv2.putText(image.image, str(last_info.track_id) + ' ' + str([last_info.class_id]) +
#                        " " + "{:.2f}".format(last_info.confidence),
#                        (int(last_info.bounding_box[0]), int(last_info.bounding_box[1]) - 10), cv2.FONT_HERSHEY_SIMPLEX,
#                        1,
#                        (0, 0, 255), 2)

            preview_img = QTableWidgetItem()
            preview_img.setData(Qt.ItemDataRole.DecorationRole, pixmap)
            lost_pixmap = QPixmap()
            if record[lost_img_idx]:
                lost_pixmap.load(os.path.join(root, record[lost_img_idx]))
            lost_img = QTableWidgetItem()
            lost_img.setData(Qt.ItemDataRole.DecorationRole, lost_pixmap)

            row = self.table.rowCount()
            self.table.insertRow(row)
            res_str = ('Object Id=' + str(record[id_idx]) + ', class: ' + str(record[
                                                                                  class_idx])) + ' conf: ' + "{:1.2f}".format(
                record[conf_idx])
            self.table.setItem(row, 0, QTableWidgetItem(info_str))
            self.table.setItem(row, 1, QTableWidgetItem(record[time_idx].strftime('%H:%M:%S %d/%m/%Y')))
            #if record[time_lost_idx]:
            #    self.table.setItem(row, 2, QTableWidgetItem(record[time_lost_idx].strftime('%H:%M:%S %d/%m/%Y')))
            #else:
            #    self.table.setItem(row, 2, QTableWidgetItem(record[time_lost_idx]))
            self.table.setItem(row, 2, QTableWidgetItem(res_str))
            self.table.setItem(row, 3, preview_img)
            #self.table.setItem(row, 5, lost_img)
            # self.table.setRowHeight(row, 150)
        if len(records)>0:
            record = records[-1]
            if record[count_idx] > last_row:
                last_row = records[-1][count_idx]
        self.last_row_db = last_row
        # self.table.resizeRowsToContents()
