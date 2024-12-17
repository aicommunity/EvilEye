import datetime
import os
from psycopg2 import sql
from utils import event
from utils import utils
from PyQt6.QtCore import QDate, Qt
from PyQt6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QTabWidget, QPushButton,
    QSizePolicy, QDateTimeEdit, QHeaderView, QComboBox, QTableView, QStyledItemDelegate,
    QTableWidget, QTableWidgetItem, QApplication, QAbstractItemView, QMessageBox
)
from PyQt6.QtGui import QPixmap, QPainter, QPen
from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QPoint, QSize, QVariant, QModelIndex
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
from visualizer.table_updater_view import TableUpdater


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def paint(self, painter, option, index):
        if index.isValid():
            path = index.data(Qt.ItemDataRole.DisplayRole)
            pixmap = QPixmap()
            if path:
                pixmap.load(path)
                painter.drawPixmap(option.rect, pixmap)
            else:
                return


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        return value.toString(Qt.DateFormat.ISODate)


class ImageWindow(QLabel):
    def __init__(self, image, box, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Image')
        self.setFixedSize(900, 600)
        self.image_path = None
        self.label = QLabel()
        self.pixmap = QPixmap(image)
        self.pixmap = self.pixmap.scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio)
        qp = QPainter(self.pixmap)
        pen = QPen(Qt.GlobalColor.green, 2)
        qp.setPen(pen)
        qp.drawRect(int(box[0] * self.pixmap.width()), int(box[1] * self.pixmap.height()),
                    int((box[2] - box[0]) * self.pixmap.width()), int((box[3] - box[1]) * self.pixmap.height()))
        qp.end()
        self.label.setPixmap(self.pixmap)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()


class CustomPixmap(QPixmap):
    def __init__(self, file=None, obj_box=None):
        super().__init__(file)
        if obj_box is None:
            obj_box = []
        self.file_path = file
        self.box = obj_box

    def set_path(self, file_path):
        self.file_path = file_path

    def get_file_path(self):
        return self.file_path

    def get_box(self):
        return self.box

    def set_box(self, obj_box):
        self.box = obj_box


class ImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.pixmap_data = []

    def setPixmap(self, pixmap: CustomPixmap) -> None:
        super().setPixmap(pixmap)
        self.pixmap_data = [pixmap.get_file_path(), pixmap.get_box()]

    def pixmap(self) -> tuple[QPixmap, str, list[int]]:
        file_path, box = self.pixmap_data
        return super().pixmap(), file_path, box


# class CustomModel(QSqlQueryModel):
#     def data(self, idx: QModelIndex, role: int):
#         if not idx.isValid():
#             return QVariant()
#         if idx.column() == 2:
#             preview_path = super().data(idx, Qt.ItemDataRole.DisplayRole)
#             print(preview_path)
#             pixmap = QPixmap()
#             if preview_path:
#                 pixmap.load(preview_path)
#             return pixmap
#         return super().data(idx, role)

class HandlerJournal(QWidget):
    retrieve_data_signal = pyqtSignal()

    preview_width = 300
    preview_height = 150

    def __init__(self, db_controller, table_name, params, table_params, parent=None):
        super().__init__()
        self.db_controller = db_controller
        self.table_updater = TableUpdater(table_name, self._insert_rows, self._update_on_lost)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._update_table)

        self.params = params
        self.db_params = (self.params['database']['user_name'], self.params['database']['password'],
                          self.params['database']['database_name'], self.params['database']['host_name'],
                          self.params['database']['port'], self.params['database']['image_dir'])
        self.username, self.password, self.db_name, self.host, self.port, self.image_dir = self.db_params
        self.db_table_params = table_params
        self.table_name = table_name
        self.table_data_thread = None

        self.db = QSqlDatabase.addDatabase("QPSQL")
        self.db.setHostName("localhost")
        self.db.setDatabaseName("evil_eye_db")
        self.db.setUserName("postgres")
        self.db.setPassword("12345")
        self.db.setPort(5432)
        if not self.db.open():
            QMessageBox.critical(
                None,
                "QTableView Example - Error!",
                "Database Error: %s" % self.db.lastError().databaseText(),
            )

        self.source_name_id_address = self._create_dict_source_name_address_id()

        self.last_row_db = 0
        self.data_for_update = []
        self.last_update_time = None
        self.update_rate = 10
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False
        self.image_win = None

        self._setup_filter()
        self._setup_table()
        self._setup_time_layout()
        # print(self.search_button.mapToParent(self.search_button.pos()).x())
        # self.filters_window = FiltersWindow(list(self.source_name_id.keys()),
        #                                     self._filter_by_camera)
        self.filter_displayed = False

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.time_layout)
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self.retrieve_data_signal.connect(self._retrieve_data)

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
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultSectionSize(HandlerJournal.preview_height)
        h_header.setDefaultSectionSize(HandlerJournal.preview_width)

        self.delegate = ImageDelegate(None)
        self.date_delegate = DateTimeDelegate(None)
        self.table.setItemDelegateForColumn(3, self.date_delegate)
        self.table.setItemDelegateForColumn(4, self.date_delegate)
        self.table.setItemDelegateForColumn(5, self.delegate)
        self.table.setItemDelegateForColumn(6, self.delegate)

    def _setup_model(self):
        self.model = QSqlQueryModel()
        query = QSqlQuery()
        query.prepare('SELECT source_name, CAST(\'Event\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || confidence AS information,'
                      'time_stamp, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)
        self.model.setHeaderData(0, Qt.Orientation.Horizontal, self.tr('Name'))
        self.model.setHeaderData(1, Qt.Orientation.Horizontal, self.tr('Event'))
        self.model.setHeaderData(2, Qt.Orientation.Horizontal, self.tr('Information'))
        self.model.setHeaderData(3, Qt.Orientation.Horizontal, self.tr('Time'))
        self.model.setHeaderData(4, Qt.Orientation.Horizontal, self.tr('Time lost'))
        self.model.setHeaderData(5, Qt.Orientation.Horizontal, self.tr('Preview'))
        self.model.setHeaderData(6, Qt.Orientation.Horizontal, self.tr('Lost preview'))

    def _setup_filter(self):
        self.filters = QComboBox()
        self.filters.setMinimumWidth(100)
        filter_names = list(self.source_name_id_address.keys())
        filter_names.insert(0, 'All')
        self.filters.addItems(filter_names)

        self.filters.currentTextChanged.connect(self._filter_by_camera)
        self.camera_label = QLabel('Display camera:')

        self.camera_filter_layout = QHBoxLayout()
        self.camera_filter_layout.addWidget(self.camera_label)
        self.camera_filter_layout.addWidget(self.filters)
        self.camera_filter_layout.addStretch(1)

    def _setup_time_layout(self):
        self._setup_datetime()
        self._setup_buttons()

        self.time_layout = QHBoxLayout()
        self.time_layout.addWidget(self.start_time)
        self.time_layout.addWidget(self.finish_time)
        self.time_layout.addWidget(self.reset_button)
        self.time_layout.addWidget(self.search_button)
        self.time_layout.addLayout(self.camera_filter_layout)

    def _setup_datetime(self):
        self.start_time = QDateTimeEdit()
        self.start_time.setMinimumWidth(200)
        self.start_time.setCalendarPopup(True)
        self.start_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.start_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.start_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.start_time.setKeyboardTracking(False)
        self.start_time.dateTimeChanged.connect(self.start_time_update)

        self.finish_time = QDateTimeEdit()
        self.finish_time.setMinimumWidth(200)
        self.finish_time.setCalendarPopup(True)
        self.finish_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.finish_time.setMaximumDate(QDate.currentDate().addDays(365))
        self.finish_time.setDisplayFormat("hh:mm:ss dd/MM/yyyy")
        self.finish_time.setKeyboardTracking(False)
        self.finish_time.dateTimeChanged.connect(self.finish_time_update)

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

    @pyqtSlot(int, int)
    def _display_image(self, row, col):
        # print(type(self.table.cellWidget(row, col)))
        widget = self.table.cellWidget(row, col)
        if type(widget) == ImageLabel:
            pixmap, file_path, box = widget.pixmap()
            if not file_path:
                return
            previews_folder_path, file_name = os.path.split(file_path)
            beg = file_name.find('preview')
            end = beg + len('preview')
            new_file_name = file_name[:beg] + 'frame' + file_name[end:]
            date_folder_path, preview_folder_name = os.path.split(os.path.normpath(previews_folder_path))
            beg = preview_folder_name.find('previews')
            file_folder_name = preview_folder_name[:beg] + 'frames'
            res_image_path = os.path.join(date_folder_path, file_folder_name, new_file_name)
            self.image_win = ImageWindow(res_image_path, box)
            self.image_win.show()

    @pyqtSlot()
    def _show_filters(self):
        if not self.filter_displayed:
            self.filters_window.show()
            self.filter_displayed = True
        else:
            self.filters_window.hide()
            self.filter_displayed = False

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
            # self.table.setRowCount(0)
            # self.last_row_db = 0
            self._retrieve_data()
            self.block_updates = False

    @pyqtSlot()
    def _filter_by_time(self):
        if not self.start_time_updated or not self.finish_time_updated:
            return
        self._filter_records(self.start_time.dateTime().toPyDateTime(), self.finish_time.dateTime().toPyDateTime())

    @pyqtSlot()
    def _update_table(self):
        if not self.block_updates:
            self._retrieve_data()

    @pyqtSlot(str)
    def _filter_by_camera(self, camera_name):
        if not self.isVisible():
            return

        fields = self.db_table_params.keys()
        if camera_name == 'All':
            self._filter_records(self.current_start_time, self.current_end_time)
            return

        source_id, full_address = self.source_name_id_address[camera_name]
        # print(camera_name, source_id, full_address)
        query = QSqlQuery()
        query.prepare('SELECT source_name, CAST(\'Event\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || confidence AS information,'
                      'time_stamp, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE (time_stamp BETWEEN :start AND :finish) AND (source_id = :src_id) '
                      'AND (camera_full_address = :address) ORDER BY time_stamp DESC')
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":src_id", source_id)
        query.bindValue(":address", full_address)
        query.exec()
        self.model.setQuery(query)

    def _filter_records(self, start_time, finish_time):
        self.current_start_time = start_time
        self.current_end_time = finish_time
        fields = self.db_table_params.keys()
        query = QSqlQuery()
        query.prepare('SELECT source_name, CAST(\'Event\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || confidence AS information,'
                      'time_stamp, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC')
        query.bindValue(":start", start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", finish_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    def _retrieve_data(self):
        if not self.isVisible():
            return
        # fields = self.db_table_params.keys()
        query = QSqlQuery()
        query.prepare('SELECT source_name, CAST(\'Event\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || confidence AS information,'
                      'time_stamp, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    @pyqtSlot()
    def _insert_rows(self):
        if self.block_updates or not self.isVisible() or self.update_timer.isActive():
            return
        self.update_timer.start(10000)
        self.update_timer.setSingleShot(True)

        # self.table.setUpdatesEnabled(False)
        # # self.table.blockSignals(True)
        # self._append_rows(records)
        # self.table.setUpdatesEnabled(True)
        # # self.table.blockSignals(False)
        # QApplication.processEvents()

    @pyqtSlot()
    def _update_on_lost(self):
        if self.block_updates or not self.isVisible() or self.update_timer.isActive():
            return
        self.update_timer.start(10000)
        print('Timer_started')

    def _append_rows(self, records):
        info_str = 'Event'
        fields = list(self.db_table_params.keys())
        sources_params = self.params['sources']
        count_idx = 0
        id_idx = fields.index('object_id')
        box_idx = fields.index('bounding_box')
        lost_box_idx = fields.index('lost_bounding_box')
        source_name_idx = fields.index('source_name')
        conf_idx = fields.index('confidence')
        class_idx = fields.index('class_id')
        time_idx = fields.index('time_stamp')
        time_lost_idx = fields.index('time_lost')
        img_path_idx = fields.index('preview_path')
        lost_img_idx = fields.index('lost_preview_path')
        root = self.image_dir

        if records is None:
            return

        last_row = self.last_row_db
        for record in records:
            # print(record)
            if record[count_idx] <= last_row:
                continue

            pixmap = CustomPixmap(os.path.join(root, record[img_path_idx]), obj_box=record[box_idx])
            preview_img = ImageLabel()
            preview_img.setPixmap(pixmap)
            lost_pixmap = CustomPixmap()
            if record[lost_img_idx]:
                lost_pixmap.load(os.path.join(root, record[lost_img_idx]))
                lost_pixmap.set_path(os.path.join(root, record[lost_img_idx]))
                lost_pixmap.set_box(obj_box=record[lost_box_idx])
            lost_img = ImageLabel()
            lost_img.setPixmap(lost_pixmap)

            source_name = record[source_name_idx]
            self.table.insertRow(0)
            res_str = (('Object Id=' + str(record[id_idx]) + ', class: ' + str(record[class_idx])) +
                       ' conf: ' + "{:1.2f}".format(record[conf_idx]))
            self.table.setItem(0, 0, QTableWidgetItem(source_name))
            self.table.setItem(0, 1, QTableWidgetItem(info_str))
            self.table.setItem(0, 2, QTableWidgetItem(record[time_idx].strftime('%H:%M:%S %d/%m/%Y')))
            if record[time_lost_idx]:
                self.table.setItem(0, 3, QTableWidgetItem(record[time_lost_idx].strftime('%H:%M:%S %d/%m/%Y')))
            else:
                self.table.setItem(0, 3, QTableWidgetItem(record[time_lost_idx]))
            self.table.setItem(0, 4, QTableWidgetItem(res_str))
            self.table.setCellWidget(0, 5, preview_img)
            self.table.setCellWidget(0, 6, lost_img)
            # self.table.setRowHeight(row, 150)
        if len(records) > 0:
            record = records[-1]
            if record[count_idx] > last_row:
                last_row = records[-1][count_idx]
        self.last_row_db = last_row
        # self.table.resizeRowsToContents()

    def close(self):
        self._update_job_first_last_records()
        self.db.close()

    def _create_dict_source_name_address_id(self):
        camera_address_id_name = {}
        sources_params = self.params['sources']

        for source in sources_params:
            address = source['camera']
            for src_id, src_name in zip(source['source_ids'], source['source_names']):
                camera_address_id_name[src_name] = (src_id, address)
        return camera_address_id_name

    def _update_job_first_last_records(self):
        job_id = self.db_controller.get_job_id()
        update_query = ''
        data = None

        # Получаем номер последней записи в данном запуске
        last_obj_query = sql.SQL('''SELECT MAX(record_id) from objects WHERE job_id = %s''')
        records = self.db_controller.query(last_obj_query, (job_id,))
        last_record = records[0][0]
        if not last_record:  # Обновляем информацию о последней записи, если записей не было, то -1
            update_query = sql.SQL('UPDATE jobs SET first_record = -1, last_record = -1 WHERE job_id = %s;')
            data = (job_id,)
        else:
            update_query = sql.SQL('UPDATE jobs SET last_record = %s WHERE job_id = %s;')
            data = (last_record, job_id)

        self.db_controller.query(update_query, data)
