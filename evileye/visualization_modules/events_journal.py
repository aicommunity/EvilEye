import datetime
import os
from ..utils import threading_events

try:
    from PyQt6.QtCore import QDate, QDateTime, QPointF
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QComboBox, QTableView, QStyledItemDelegate, QMessageBox
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex, QSize
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QDate, QDateTime, QPointF
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QComboBox, QTableView, QStyledItemDelegate, QMessageBox
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex, QSize
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from .table_updater_view import TableUpdater
from ..core.logger import get_module_logger
import logging


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, image_dir=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.image_delegate"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.image_dir = image_dir

    def paint(self, painter, option, index):
        if not index.isValid():
            return
            
        path = index.data(Qt.ItemDataRole.DisplayRole)
        if not path:
            return
            
        full_path = os.path.join(self.image_dir, path)
        if not os.path.exists(full_path):
            return
            
        # Load image
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return

        # Calculate target rect with aspect fit
        cell_rect = option.rect
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return
            
        cell_w = cell_rect.width()
        cell_h = cell_rect.height()
        scale = min(cell_w / img_w, cell_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = cell_rect.x() + (cell_w - draw_w) // 2
        draw_y = cell_rect.y() + (cell_h - draw_h) // 2
        
        # Draw image
        painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
        
        # For preview images, coordinates are normalized relative to the original image size
        # but we need to scale them to the preview image size
        # Preview images are typically 320x240 or 300x150, but original images are much larger
        # So we need to use the preview image dimensions for coordinate conversion
        
        # Try to get bounding box from database for this image
        try:
            from PyQt6.QtSql import QSqlDatabase, QSqlQuery
        except ImportError:
            from PyQt5.QtSql import QSqlDatabase, QSqlQuery
            
        box = None
        zone_coords = None
        
        # Query database for bounding box based on event type and column
        query = QSqlQuery(QSqlDatabase.database('events_conn'))
        # Determine event type from model (column 1 holds 'Event') and current column (5 Preview, 6 Lost preview)
        try:
            event_type = index.model().index(index.row(), 1).data()
        except Exception:
            event_type = None
        col = index.column()
        if event_type == 'ZoneEvent':
            if col == 5:
                query.prepare('SELECT box_entered, zone_coords FROM zone_events WHERE preview_path_entered = :path')
            else:
                query.prepare('SELECT box_left, zone_coords FROM zone_events WHERE preview_path_left = :path')
        elif event_type == 'AttributeEvent':
            if col == 5:
                query.prepare('SELECT box_found FROM attribute_events WHERE preview_path_found = :path')
            else:
                query.prepare('SELECT box_finished FROM attribute_events WHERE preview_path_finished = :path')
        elif event_type == 'ObjectEvent':
            if col == 5:
                query.prepare('SELECT bounding_box FROM objects WHERE preview_path = :path')
            else:
                query.prepare('SELECT lost_bounding_box FROM objects WHERE lost_preview_path = :path')
        else:
            # Fallback by guessing from column name; FOV/Camera have no bbox
            query = None
        if query is not None:
            query.bindValue(':path', path)
            if query.exec() and query.next():
                value0 = query.value(0)
                # Robust parse for box
                if value0 is not None:
                    try:
                        if isinstance(value0, str):
                            box_str = value0.replace('{', '').replace('}', '')
                            box = [float(coord) for coord in box_str.split(',')]
                        elif isinstance(value0, (list, tuple)):
                            box = [float(v) for v in value0]
                        elif hasattr(value0, 'toString'):
                            s = value0.toString()
                            box_str = str(s).replace('{', '').replace('}', '')
                            box = [float(coord) for coord in box_str.split(',')]
                        else:
                            s = str(value0)
                            box_str = s.replace('{', '').replace('}', '')
                            parts = [p for p in box_str.split(',') if p.strip()]
                            if len(parts) == 4:
                                box = [float(coord) for coord in parts]
                    except Exception:
                        box = None
                # Zone coords parsing
                if event_type == 'ZoneEvent' and query.record().count() > 1:
                    value1 = query.value(1)
                    try:
                        if isinstance(value1, str):
                            s = value1.strip()
                            # Expect something like "{{x,y},{x,y},...}"
                            s = s.strip('{}')
                            points_str = [p.strip('{} ') for p in s.split('},')]
                            zone_coords = []
                            for ps in points_str:
                                parts = [pp for pp in ps.split(',') if pp.strip()]
                                if len(parts) == 2:
                                    zone_coords.append((float(parts[0]), float(parts[1])))
                        elif isinstance(value1, (list, tuple)):
                            zone_coords = [(float(p[0]), float(p[1])) for p in value1 if isinstance(p, (list, tuple)) and len(p) == 2]
                        elif hasattr(value1, 'toString'):
                            s = str(value1.toString()).strip('{}')
                            points_str = [p.strip('{} ') for p in s.split('},')]
                            zone_coords = []
                            for ps in points_str:
                                parts = [pp for pp in ps.split(',') if pp.strip()]
                                if len(parts) == 2:
                                    zone_coords.append((float(parts[0]), float(parts[1])))
                    except Exception:
                        zone_coords = None
        
        # Draw bounding box if available
        if box and len(box) == 4:
            painter.setPen(QPen(QColor(0, 255, 0), 2))  # Green for bbox
            # Use the same logic as in objects journal ImageWindow
            # Coordinates are in format [x1, y1, x2, y2] (top-left and bottom-right)
            x1, y1, x2, y2 = box
            
            # Scale coordinates to draw area (same as ImageWindow logic)
            x = draw_x + int(x1 * draw_w)
            y = draw_y + int(y1 * draw_h)
            w = int((x2 - x1) * draw_w)
            h = int((y2 - y1) * draw_h)
            
            painter.drawRect(x, y, w, h)
        
        # Draw zone if available
        if zone_coords:
            painter.setPen(QPen(QColor(255, 0, 0), 2))  # Red for zone
            painter.setBrush(QBrush(QColor(255, 0, 0, 64)))  # Semi-transparent red fill
            polygon = QPolygonF()
            for point in zone_coords:
                px, py = point
                
                # Use the same logic as bounding box - scale to draw area
                x = draw_x + int(px * draw_w)
                y = draw_y + int(py * draw_h)
                
                polygon.append(QPointF(x, y))
            painter.drawPolygon(polygon)

    def sizeHint(self, option, index) -> QSize:
        if index.isValid():
            if index.data(Qt.ItemDataRole.DisplayRole):
                return QSize(300, 150)
            else:
                return super().sizeHint(option, index)


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        if hasattr(value, 'toString'):
            return value.toString(Qt.DateFormat.ISODate)
        else:
            # Value is already a string
            return str(value)


class ImageWindow(QLabel):
    def __init__(self, image, box=None, zone_coords=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Image')
        self.setFixedSize(900, 600)
        self.image_path = None
        self.label = QLabel()
        base_pixmap = QPixmap(image)
        scaled = base_pixmap.scaled(self.width(), self.height(), Qt.AspectRatioMode.KeepAspectRatio)
        qp = QPainter()
        try:
            qp.begin(scaled)
            if zone_coords:
                coords = [QPointF(point[0] * scaled.width(), point[1] * scaled.height()) for point in zone_coords]
                qp.setPen(QPen(Qt.GlobalColor.red))
                qp.setBrush(QBrush(QColor(255, 0, 0, 64)))
                qp.drawPolygon(coords)
            if box is not None:
                pen = QPen(Qt.GlobalColor.green, 2)
                qp.setPen(pen)
                qp.setBrush(QBrush())
                qp.drawRect(int(box[0] * scaled.width()), int(box[1] * scaled.height()),
                            int((box[2] - box[0]) * scaled.width()), int((box[3] - box[1]) * scaled.height()))
        finally:
            qp.end()
        self.label.setPixmap(scaled)
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()


class EventsJournal(QWidget):
    retrieve_data_signal = pyqtSignal()

    preview_width = 300
    preview_height = 150

    def __init__(self, journal_adapters: list, db_controller, table_name, params, database_params, table_params, parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__()
        base_name = "evileye.events_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.db_controller = db_controller
        self.journal_adapters = journal_adapters

        # Сопоставляет имена событий с соответствующими им адаптерами
        self.events_adapters = {adapter.get_event_name(): adapter for adapter in self.journal_adapters}
        # Сопоставляет имена событий с именами таблиц БД
        self.events_tables = {adapter.get_event_name(): adapter.get_table_name() for adapter in self.journal_adapters}

        self.table_updater = TableUpdater()
        self.table_updater.append_event_signal.connect(self._insert_rows)
        self.table_updater.update_event_signal.connect(self._update_on_lost)

        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_table)

        self.params = params
        self.database_params = database_params
        self.db_params = (self.database_params['database']['user_name'], self.database_params['database']['password'],
                          self.database_params['database']['database_name'], self.database_params['database']['host_name'],
                          self.database_params['database']['port'], self.database_params['database']['image_dir'])
        self.username, self.password, self.db_name, self.host, self.port, self.image_dir = self.db_params
        self.db_table_params = table_params
        self.table_name = table_name
        self.table_data_thread = None

        self._connect_to_db()
        self.source_name_id_address = self._create_dict_source_name_address_id()

        self.last_row_db = 0
        self.data_for_update = []
        self.last_update_time = None
        self.update_rate = 10
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        self.start_time_updated = False
        self.finish_time_updated = False
        self.block_updates = False
        self.image_win = None

        self._setup_filter()
        self._setup_table()
        self._setup_time_layout()
        self.filter_displayed = False

        self.layout = QVBoxLayout()
        self.layout.addLayout(self.time_layout)
        self.layout.addWidget(self.table)
        self.setLayout(self.layout)

        self.retrieve_data_signal.connect(self._retrieve_data)
        self.table.doubleClicked.connect(self._display_image)
        
        # Add automatic data refresh
        self.refresh_timer = QTimer()
        self.refresh_timer.timeout.connect(self._auto_refresh_data)
        self.refresh_timer.start(5000)  # Refresh every 5 seconds
        
        # Initial data load
        self._retrieve_data()

    def _connect_to_db(self):
        # Check if connection already exists
        if 'events_conn' in QSqlDatabase.connectionNames():
            return
            
        db = QSqlDatabase.addDatabase("QPSQL", 'events_conn')
        db.setHostName(self.host)
        db.setDatabaseName(self.db_name)
        db.setUserName(self.username)
        db.setPassword(self.password)
        db.setPort(self.port)
        if not db.open():
            QMessageBox.critical(
                None,
                "Events journal - Error!",
                "Database Error: %s" % db.lastError().databaseText(),
            )

    def _setup_table(self):
        self._setup_model()

        self.table = QTableView()
        self.table.setModel(self.model)
        # header = self.table.verticalHeader()
        h_header = self.table.horizontalHeader()
        v_header = self.table.verticalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        h_header.setDefaultSectionSize(EventsJournal.preview_width)
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.image_delegate = ImageDelegate(None, image_dir=self.image_dir, logger_name="image_delegate", parent_logger=self.logger)
        self.date_delegate = DateTimeDelegate(None)
        self.table.setItemDelegateForColumn(2, self.date_delegate)
        self.table.setItemDelegateForColumn(3, self.date_delegate)
        self.table.setItemDelegateForColumn(5, self.image_delegate)
        self.table.setItemDelegateForColumn(6, self.image_delegate)

    def _setup_model(self):
        self.model = QSqlQueryModel()

        query_string = 'SELECT * FROM ('
        for adapter in self.journal_adapters:
            adapter_query = adapter.select_query()
            query_string += adapter_query + ' UNION '
        query_string = query_string.removesuffix(' UNION ')
        query_string += ') AS temp ORDER BY time_stamp DESC;'
        
        query = QSqlQuery(QSqlDatabase.database('events_conn'))
        if query.prepare(query_string):
            if query.exec():
                self.model.setQuery(query)
            else:
                self.logger.error(f"SQL Error: {query.lastError().text()}")
        else:
            self.logger.error(f"SQL Prepare Error: {query.lastError().text()}")
        self.model.setHeaderData(0, Qt.Orientation.Horizontal, self.tr('Time'))
        self.model.setHeaderData(1, Qt.Orientation.Horizontal, self.tr('Event'))
        self.model.setHeaderData(2, Qt.Orientation.Horizontal, self.tr('Event Details'))
        self.model.setHeaderData(3, Qt.Orientation.Horizontal, self.tr('Time lost'))
        self.model.setHeaderData(4, Qt.Orientation.Horizontal, self.tr('Information'))
        self.model.setHeaderData(5, Qt.Orientation.Horizontal, self.tr('Preview'))
        self.model.setHeaderData(6, Qt.Orientation.Horizontal, self.tr('Lost preview'))

    def _setup_filter(self):
        self.filters = QComboBox()
        self.filters.setMinimumWidth(100)
        filter_names = list(self.source_name_id_address.keys())
        filter_names.insert(0, 'All')
        self.filters.addItems(filter_names)

        # self.filters.currentTextChanged.connect(self._filter_by_camera)
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
        self.start_time.setDateTime(self.current_start_time)
        self.start_time.setMinimumDate(QDate.currentDate().addDays(-365))
        self.start_time.setMaximumDate(QDate.currentDate().addDays(365))
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
        self.table.resizeRowsToContents()
        show_event.accept()
#        self.start_time_update()
#        self.finish_time_update()
#        self._filter_by_time()

    @pyqtSlot(QModelIndex)
    def _display_image(self, index):
        col = index.column()
        # Allow double click on Preview (5) and Lost preview (6)
        if col != 5 and col != 6:
            return

        path = index.data()
        if not path:
            return

        # Fetch overlay data using event type column (1)
        box = None
        zone_coords = None
        query = QSqlQuery(QSqlDatabase.database('events_conn'))
        try:
            event_type = index.model().index(index.row(), 1).data()
        except Exception:
            event_type = None
        if event_type == 'ZoneEvent':
            if col == 5:
                query.prepare('SELECT box_entered, zone_coords from zone_events WHERE preview_path_entered = :path')
            else:
                query.prepare('SELECT box_left, zone_coords from zone_events WHERE preview_path_left = :path')
        elif event_type == 'AttributeEvent':
            if col == 5:
                query.prepare('SELECT box_found FROM attribute_events WHERE preview_path_found = :path')
            else:
                query.prepare('SELECT box_finished FROM attribute_events WHERE preview_path_finished = :path')
        elif event_type == 'ObjectEvent':
            if col == 5:
                query.prepare('SELECT bounding_box from objects WHERE preview_path = :path')
            else:
                query.prepare('SELECT lost_bounding_box from objects WHERE lost_preview_path = :path')
        else:
            # FOV/Camera events have no bbox
            query = None
        query.bindValue(':path', path)
        if query is not None and query.exec() and query.next():
            # Parse box robustly
            value0 = query.value(0)
            try:
                if isinstance(value0, str):
                    s = value0.replace('{', '').replace('}', '')
                    parts = [p for p in s.split(',') if p.strip()]
                    if len(parts) == 4:
                        box = [float(p) for p in parts]
                elif isinstance(value0, (list, tuple)):
                    if len(value0) == 4:
                        box = [float(v) for v in value0]
                elif hasattr(value0, 'toString'):
                    s = str(value0.toString()).replace('{', '').replace('}', '')
                    parts = [p for p in s.split(',') if p.strip()]
                    if len(parts) == 4:
                        box = [float(p) for p in parts]
                else:
                    s = str(value0).replace('{', '').replace('}', '')
                    parts = [p for p in s.split(',') if p.strip()]
                    if len(parts) == 4:
                        box = [float(p) for p in parts]
            except Exception:
                box = None
            # Parse zone coords if available
            if 'zone' in path and query.record().count() > 1:
                value1 = query.value(1)
                try:
                    if isinstance(value1, str):
                        s = value1.strip().strip('{}')
                        pts = [p.strip('{} ') for p in s.split('},')]
                        tmp = []
                        for ps in pts:
                            parts = [pp for pp in ps.split(',') if pp.strip()]
                            if len(parts) == 2:
                                tmp.append((float(parts[0]), float(parts[1])))
                        if tmp:
                            zone_coords = tmp
                    elif isinstance(value1, (list, tuple)):
                        zone_coords = [(float(p[0]), float(p[1])) for p in value1 if isinstance(p, (list, tuple)) and len(p) == 2]
                    elif hasattr(value1, 'toString'):
                        s = str(value1.toString()).strip('{}')
                        pts = [p.strip('{} ') for p in s.split('},')]
                        tmp = []
                        for ps in pts:
                            parts = [pp for pp in ps.split(',') if pp.strip()]
                            if len(parts) == 2:
                                tmp.append((float(parts[0]), float(parts[1])))
                        if tmp:
                            zone_coords = tmp
                except Exception:
                    zone_coords = None

        image_path = os.path.join(self.image_dir, path)
        previews_folder_path, file_name = os.path.split(image_path)
        beg = file_name.find('preview')
        end = beg + len('preview')
        new_file_name = file_name[:beg] + 'frame' + file_name[end:]
        date_folder_path, preview_folder_name = os.path.split(os.path.normpath(previews_folder_path))
        beg = preview_folder_name.find('previews')
        file_folder_name = preview_folder_name[:beg] + 'frames'
        res_image_path = os.path.join(date_folder_path, file_folder_name, new_file_name)

        # Attribute events already handled above; no extra fetch needed
        self.image_win = ImageWindow(res_image_path, box, zone_coords)
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
        threading_events.notify('handler new object')

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
        self.start_time_updated = False
        self.finish_time_updated = False

    @pyqtSlot()
    def _update_table(self):
        if not self.block_updates:
            self._retrieve_data()

    @pyqtSlot(str)
    def _filter_by_camera(self, camera_name):
        if not self.isVisible():
            return
        self.block_updates = True

        fields = self.db_table_params.keys()
        if camera_name == 'All':
            if (self.current_start_time == datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min) and
                    self.current_end_time == datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)):
                self.block_updates = False
            self._filter_records(self.current_start_time, self.current_end_time)
            return

        source_id, full_address = self.source_name_id_address[camera_name]
        # self.logger.debug(f"{camera_name}, {source_id}, {full_address}")
        query = QSqlQuery(QSqlDatabase.database('events_conn'))
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
        query = QSqlQuery(QSqlDatabase.database('events_conn'))
        query_string = 'SELECT * FROM ('
        for adapter in self.journal_adapters:
            adapter_query = adapter.select_query()
            query_string += adapter_query + ' UNION '
        query_string = query_string.removesuffix(' UNION ')
        query_string += ') AS temp WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC;'
        query.prepare(query_string)
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    def _auto_refresh_data(self):
        """Automatically refresh data every 5 seconds"""
        try:
            self._retrieve_data()
        except Exception as e:
            self.logger.error(f"Auto-refresh error: {e}")

    def _retrieve_data(self):
        try:
            # Build query string
            query_string = 'SELECT * FROM ('
            for adapter in self.journal_adapters:
                adapter_query = adapter.select_query()
                query_string += adapter_query + ' UNION '
            query_string = query_string.removesuffix(' UNION ')
            query_string += ') AS temp WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC;'
            
            # Set time range
            self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
            self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
            
            # Update filter controls
            self.start_time.setDateTime(
                QDateTime.fromString(self.current_start_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))
            self.finish_time.setDateTime(
                QDateTime.fromString(self.current_end_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))

            # Check if database connection exists
            if 'events_conn' not in QSqlDatabase.connectionNames():
                self._connect_to_db()
            
            # Create and execute query in one go
            query = QSqlQuery(QSqlDatabase.database('events_conn'))
            query.prepare(query_string)
            query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
            query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
            
            if query.exec():
                self.model.setQuery(query)
            else:
                self.logger.error(f"Events query failed: {query.lastError().text()}")
                # Check if connection is still valid
                if 'events_conn' not in QSqlDatabase.connectionNames():
                    self._connect_to_db()
                
        except Exception as e:
            self.logger.error(f"Retrieve data error: {e}")

    @pyqtSlot()
    def _insert_rows(self):
        if self.block_updates or not self.isVisible() or self.update_timer.isActive():
            return
        self.update_timer.start(10000)

    @pyqtSlot()
    def _update_on_lost(self):
        if self.block_updates or not self.isVisible() or self.update_timer.isActive():
            return
        self.update_timer.start(10000)

    def showEvent(self, event):
        """Called when the widget is shown"""
        super().showEvent(event)
        self._retrieve_data()

    def close(self):
        # self._update_job_first_last_records()
        if hasattr(self, 'refresh_timer'):
            self.refresh_timer.stop()
        QSqlDatabase.removeDatabase('events_conn')

    def _create_dict_source_name_address_id(self):
        camera_address_id_name = {}
        sources_params = self.params.get('pipeline', {}).get('sources', [])

        for source in sources_params:
            address = source['camera']
            for src_id, src_name in zip(source['source_ids'], source['source_names']):
                camera_address_id_name[src_name] = (src_id, address)
        return camera_address_id_name

    # def _update_job_first_last_records(self):
    #     job_id = self.db_controller.get_job_id()
    #     update_query = ''
    #     data = None
    #
    #     # Получаем номер последней записи в данном запуске
    #     last_obj_query = sql.SQL('''SELECT MAX(record_id) from objects WHERE job_id = %s''')
    #     records = self.db_controller.query(last_obj_query, (job_id,))
    #     last_record = records[0][0]
    #     if not last_record:  # Обновляем информацию о последней записи, если записей не было, то -1
    #         update_query = sql.SQL('UPDATE jobs SET first_record = -1, last_record = -1 WHERE job_id = %s;')
    #         data = (job_id,)
    #     else:
    #         update_query = sql.SQL('UPDATE jobs SET last_record = %s WHERE job_id = %s;')
    #         data = (last_record, job_id)
    #
    #     self.db_controller.query(update_query, data)


if __name__ == '__main__':
    query = QSqlQuery("SELECT country FROM artist")
    query2 = QSqlQuery()
