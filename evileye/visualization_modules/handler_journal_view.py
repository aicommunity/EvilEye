import datetime
import os
import time
from psycopg2 import sql
from ..utils import threading_events
try:
    from PyQt6.QtCore import QDate, QDateTime
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QComboBox, QTableView, QStyledItemDelegate,
        QMessageBox, QApplication
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen
    from PyQt6.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QDate, QDateTime
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QDateTimeEdit, QHeaderView, QComboBox, QTableView, QStyledItemDelegate,
        QMessageBox, QApplication
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen
    from PyQt5.QtCore import pyqtSignal, pyqtSlot, Qt, QTimer, QModelIndex
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from .table_updater_view import TableUpdater
from .handler_journal_data_loader import HandlerJournalDataLoader
from ..core.logger import get_module_logger


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, image_dir=None, db_connection_name='obj_conn'):
        super().__init__(parent)
        self.image_dir = image_dir
        self.db_connection_name = db_connection_name

    def paint(self, painter, option, index):
        if not index.isValid():
            return

        rel_path = index.data(Qt.ItemDataRole.DisplayRole)
        if not rel_path:
            return
        full_path = os.path.join(self.image_dir, rel_path)

        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return

        # Aspect-fit target rect
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

        # Draw bbox overlay from DB (normalized [x1,y1,x2,y2])
        try:
            query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
        except Exception:
            return
        col = index.column()
        if col == 5:
            query.prepare('SELECT bounding_box from objects WHERE preview_path = :path')
        elif col == 6:
            query.prepare('SELECT lost_bounding_box from objects WHERE lost_preview_path = :path')
        else:
            return
        query.bindValue(':path', rel_path)
        if not (query.exec() and query.next()):
            return
        value = query.value(0)
        box = None
        try:
            if isinstance(value, str):
                s = value.replace('{', '').replace('}', '')
                parts = [p for p in s.split(',') if p.strip()]
                if len(parts) == 4:
                    box = [float(p) for p in parts]
            elif isinstance(value, (list, tuple)):
                if len(value) == 4:
                    box = [float(v) for v in value]
            elif hasattr(value, 'toString'):
                s = str(value.toString()).replace('{', '').replace('}', '')
                parts = [p for p in s.split(',') if p.strip()]
                if len(parts) == 4:
                    box = [float(p) for p in parts]
            else:
                s = str(value).replace('{', '').replace('}', '')
                parts = [p for p in s.split(',') if p.strip()]
                if len(parts) == 4:
                    box = [float(p) for p in parts]
        except Exception:
            box = None
        if not box or len(box) != 4:
            return
        painter.setPen(QPen(Qt.GlobalColor.green, 2))
        x1, y1, x2, y2 = box
        x = draw_x + int(x1 * draw_w)
        y = draw_y + int(y1 * draw_h)
        w = int((x2 - x1) * draw_w)
        h = int((y2 - y1) * draw_h)
        painter.drawRect(x, y, w, h)


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
    def __init__(self, image, box=None, parent=None):
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

class HandlerJournal(QWidget):
    retrieve_data_signal = pyqtSignal()

    preview_width = 300
    preview_height = 150

    def __init__(self, table_name='objects', parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("handler_journal")
        self.db_controller = None
        self.table_updater = TableUpdater()
        self.table_updater.append_object_signal.connect(self._insert_rows)
        self.table_updater.update_object_signal.connect(self._update_on_lost)

        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self._update_table)

        self.params = {}
        self.database_params = {}
        self.db_params = None
        self.username = None
        self.password = None
        self.db_name = None
        self.host = None
        self.port = None
        self.image_dir = None
        self.db_table_params = {}
        self.table_name = table_name
        self.table_data_thread = None

        # Phase 1: Initialize basic state
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
        self.filter_displayed = False
        
        # Initialize data loading state
        self._data_loaded = False
        self.source_name_id_address = {}
        self.table = None
        self.model = None
        self._data_loader = None
        
        # Show placeholder state
        self._init_ui_empty()
        
        self.retrieve_data_signal.connect(self._retrieve_data)
    
    def _init_ui_empty(self):
        """Инициализация пустого UI с placeholder"""
        placeholder_label = QLabel("Objects journal\n\nData will be loaded when controller is initialized.")
        placeholder_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        placeholder_label.setStyleSheet("font-size: 14px; padding: 20px; color: gray;")
        
        empty_layout = QVBoxLayout()
        empty_layout.addWidget(placeholder_label)
        self.setLayout(empty_layout)
    
    def set_db_controller(self, db_controller, table_name, params, database_params, table_params):
        """Установить данные из controller (вызывается после controller.init())"""
        if not db_controller:
            return
        
        # Используем утилиту для обеспечения полноты database_params
        from evileye.utils.database_config_utils import ensure_database_config_complete
        
        self.db_controller = db_controller
        self.params = params
        # Убеждаемся, что database_params содержит все необходимые ключи
        self.database_params = ensure_database_config_complete(database_params)
        self.db_table_params = table_params
        self.table_name = table_name
        
        # Получаем значения с fallback на значения по умолчанию
        db_section = self.database_params.get('database', {})
        self.db_params = (
            db_section.get('user_name', 'postgres'),
            db_section.get('password', ''),
            db_section.get('database_name', 'evil_eye_db'),
            db_section.get('host_name', 'localhost'),
            db_section.get('port', 5432),
            db_section.get('image_dir', 'EvilEyeData')
        )
        self.username, self.password, self.db_name, self.host, self.port, self.image_dir = self.db_params
        
        # Show loading state
        self._show_loading_state()
        
        # Phase 2: Start data loading in background thread
        # Передаем уже дополненный database_params
        self._data_loader = HandlerJournalDataLoader(
            db_controller, table_name, params, self.database_params, table_params,
            logger_name="handler_journal_data_loader", parent_logger=self.logger
        )
        self._data_loader.data_ready.connect(self._on_data_loaded)
        self._data_loader.progress_updated.connect(self._update_loading_progress)
        self._data_loader.start()

    def _show_loading_state(self):
        """Show loading indicator while data is being loaded"""
        self.logger.debug("_show_loading_state started")
        # Получаем существующий layout или создаем новый
        current_layout = self.layout()
        self.logger.debug(f"Current layout from self.layout(): {current_layout}")
        
        if not current_layout:
            # Если layout не существует, создаем новый
            self.logger.debug("No layout found, creating new QVBoxLayout")
            current_layout = QVBoxLayout()
            self.setLayout(current_layout)
        else:
            # Очищаем существующий layout (удаляем все элементы)
            self.logger.debug("Clearing existing layout items...")
            while current_layout.count():
                item = current_layout.takeAt(0)
                if item.widget():
                    widget = item.widget()
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
                elif item.layout():
                    # Рекурсивно очищаем вложенные layouts
                    nested_layout = item.layout()
                    while nested_layout.count():
                        nested_item = nested_layout.takeAt(0)
                        if nested_item.widget():
                            nested_widget = nested_item.widget()
                            nested_widget.hide()
                            nested_widget.setParent(None)
                            nested_widget.deleteLater()
                    nested_layout.setParent(None)
                    nested_layout.deleteLater()
        
        # Сохраняем ссылку на layout для использования в _initialize_with_data
        self._current_layout = current_layout
        self.logger.debug(f"Saved _current_layout: {self._current_layout}, id: {id(self._current_layout)}")
        
        self.loading_label = QLabel("Loading journal data...\nPlease wait...")
        self.loading_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.loading_label.setStyleSheet("font-size: 14px; padding: 20px;")
        
        # Добавляем loading_label в существующий layout (не создаем новый)
        current_layout.addWidget(self.loading_label)
        self.logger.debug("_show_loading_state completed")
    
    @pyqtSlot(str)
    def _update_loading_progress(self, message):
        """Update loading progress message"""
        if hasattr(self, 'loading_label'):
            self.loading_label.setText(f"Loading journal data...\n{message}")
    
    @pyqtSlot(dict)
    def _on_data_loaded(self, data):
        """Handle data loaded signal from background thread"""
        if data.get('error'):
            error_msg = data['error']
            self.logger.error(f"Failed to load journal data: {error_msg}")
            # Логируем ошибку вместо показа диалога
            # Keep loading state on error
            return
        
        # Store loaded data
        self.source_name_id_address = data['source_name_id_address']
        
        # Connect to database in main GUI thread (Qt requirement)
        self._db_connection_name = 'obj_conn'
        if not self._connect_to_db():
            # Логируем ошибку вместо показа диалога (уже залогировано в _connect_to_db)
            self.logger.error("Failed to connect to database for handler journal")
            return
        
        # Initialize widget with loaded data
        # Use QTimer to defer initialization to next event loop iteration
        # This ensures widget is fully added to parent before we modify its layout
        # Check if widget is ready before initializing
        if not self.isVisible() and self.parent() is None:
            self.logger.warning("Widget not yet added to parent, deferring initialization")
            QTimer.singleShot(100, self._initialize_with_data)
        else:
            QTimer.singleShot(0, self._initialize_with_data)
        
        self._data_loaded = True
        self.logger.info("Journal data loaded successfully")
    
    def _connect_to_db(self):
        """Connect to database in main GUI thread"""
        db = QSqlDatabase.addDatabase("QPSQL", self._db_connection_name)
        db.setHostName(self.host)
        db.setDatabaseName(self.db_name)
        db.setUserName(self.username)
        db.setPassword(self.password)
        db.setPort(self.port)
        if not db.open():
            error_text = db.lastError().databaseText()
            self.logger.error(f"Database connection failed: {error_text}")
            # Логируем ошибку вместо показа диалога
            return False
        return True
    
    def _initialize_with_data(self):
        """Initialize widget with loaded data"""
        try:
            self.logger.info("_initialize_with_data started")
            
            # Setup filter (requires source_name_id_address)
            self.logger.debug("Setting up filter...")
            self._setup_filter()
            self.logger.debug("Filter setup completed")
            
            # Setup time layout (doesn't require data, but needs filter)
            self.logger.debug("Setting up time layout...")
            self._setup_time_layout()
            self.logger.debug("Time layout setup completed")
            
            # Create empty table first (without model) to show UI immediately
            self.logger.debug("Creating table view...")
            self.table = QTableView()
            header = self.table.verticalHeader()
            h_header = self.table.horizontalHeader()
            h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
            h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
            header.setDefaultSectionSize(HandlerJournal.preview_height)
            h_header.setDefaultSectionSize(HandlerJournal.preview_width)
            
            self.image_delegate = ImageDelegate(None, image_dir=self.image_dir, db_connection_name=self._db_connection_name)
            self.date_delegate = DateTimeDelegate(None)
            self.table.setItemDelegateForColumn(0, self.date_delegate)
            self.table.setItemDelegateForColumn(4, self.date_delegate)
            self.table.setItemDelegateForColumn(5, self.image_delegate)
            self.table.setItemDelegateForColumn(6, self.image_delegate)
            self.logger.debug("Table view created")
            
            # Replace loading layout with actual content
            if hasattr(self, 'loading_label'):
                self.loading_label.hide()
                self.loading_label.setParent(None)
                self.loading_label.deleteLater()
                delattr(self, 'loading_label')
            
            # Получаем layout - используем сохраненную ссылку
            self.logger.debug("Getting layout...")
            current_layout = getattr(self, '_current_layout', None)
            self.logger.debug(f"_current_layout from getattr: {current_layout}, type: {type(current_layout)}")
            
            # Проверяем, что layout валиден (не None и не удален)
            if current_layout is None:
                self.logger.warning("_current_layout is None, trying self.layout()")
                current_layout = self.layout()
                self.logger.debug(f"Got layout from self.layout(): {current_layout}")
            elif not hasattr(current_layout, 'addWidget'):
                # Layout объект может быть недействителен
                self.logger.warning("_current_layout is not a valid layout object, trying self.layout()")
                current_layout = self.layout()
                self.logger.debug(f"Got layout from self.layout(): {current_layout}")
            
            # Если layout все еще не найден, создаем новый
            if current_layout is None:
                self.logger.warning("No layout found after all checks, creating new layout as fallback")
                # Используем processEvents для синхронизации Qt
                try:
                    from PyQt6.QtWidgets import QApplication
                except ImportError:
                    from PyQt5.QtWidgets import QApplication
                QApplication.processEvents()
                
                # Проверяем еще раз после processEvents
                current_layout = self.layout()
                if current_layout is None:
                    # Создаем layout только если действительно отсутствует
                    self.logger.warning("Creating new QVBoxLayout as final fallback")
                    current_layout = QVBoxLayout()
                    # Проверяем еще раз перед установкой (race condition protection)
                    if self.layout() is None:
                        self.setLayout(current_layout)
                    else:
                        # Layout появился между проверками, используем его
                        current_layout = self.layout()
            
            # Обновляем сохраненную ссылку
            self._current_layout = current_layout
            self.logger.debug("Layout obtained successfully")
            
            # Remove all items from existing layout
            self.logger.debug("Clearing existing layout items...")
            while current_layout.count():
                item = current_layout.takeAt(0)
                if item.widget():
                    widget = item.widget()
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()
                elif item.layout():
                    # Рекурсивно очищаем вложенные layouts
                    nested_layout = item.layout()
                    while nested_layout.count():
                        nested_item = nested_layout.takeAt(0)
                        if nested_item.widget():
                            nested_widget = nested_item.widget()
                            nested_widget.hide()
                            nested_widget.setParent(None)
                            nested_widget.deleteLater()
                    nested_layout.setParent(None)
                    nested_layout.deleteLater()
            self.logger.debug("Layout cleared")
            
            # Reuse existing layout (NEVER call setLayout() here - layout is already set)
            self.logger.debug("Adding time layout and table to layout...")
            current_layout.addLayout(self.time_layout)
            current_layout.addWidget(self.table)
            self.layout = current_layout
            self.logger.debug("Layout updated with new content")
            
            # Connect table signals
            self.logger.debug("Connecting table signals...")
            self.table.doubleClicked.connect(self._display_image)
            
            # Setup model synchronously (as in working commit dcc28d3c)
            self.logger.debug("Setting up model synchronously...")
            self._setup_model()
            if self.model:
                self.logger.debug("Setting model to table...")
                self.table.setModel(self.model)
                self.table.show()
                self.update()
                self.logger.debug("Model set to table successfully")
            else:
                self.logger.warning("Model is None, cannot set to table")
            
            self.logger.info("_initialize_with_data completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error in _initialize_with_data: {e}", exc_info=True)
            # Try to show error state
            try:
                error_label = QLabel(f"Error initializing journal: {str(e)}")
                error_label.setStyleSheet("color: red; padding: 20px;")
                if hasattr(self, '_current_layout') and self._current_layout:
                    while self._current_layout.count():
                        item = self._current_layout.takeAt(0)
                        if item.widget():
                            item.widget().deleteLater()
                    self._current_layout.addWidget(error_label)
            except Exception as e2:
                self.logger.error(f"Failed to show error state: {e2}", exc_info=True)
    
    def _setup_table(self):
        self._setup_model()

        self.table = QTableView()
        self.table.setModel(self.model)
        header = self.table.verticalHeader()
        h_header = self.table.horizontalHeader()
        h_header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        h_header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h_header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setDefaultSectionSize(HandlerJournal.preview_height)
        h_header.setDefaultSectionSize(HandlerJournal.preview_width)

        self.image_delegate = ImageDelegate(None, image_dir=self.image_dir, db_connection_name=self._db_connection_name)
        self.date_delegate = DateTimeDelegate(None)
        self.table.setItemDelegateForColumn(0, self.date_delegate)
        self.table.setItemDelegateForColumn(4, self.date_delegate)
        self.table.setItemDelegateForColumn(5, self.image_delegate)
        self.table.setItemDelegateForColumn(6, self.image_delegate)

    def _setup_model(self):
        self.model = QSqlQueryModel()

        query = QSqlQuery(QSqlDatabase.database(self._db_connection_name))
        query.prepare('SELECT time_stamp, CAST(\'ObjectEvent\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || ROUND(confidence::numeric, 2)'
                      ' AS information,'
                      'source_name, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish '
                      'ORDER BY time_stamp DESC')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()

        self.model.setQuery(query)
        self.model.setHeaderData(0, Qt.Orientation.Horizontal, self.tr('Time'))
        self.model.setHeaderData(1, Qt.Orientation.Horizontal, self.tr('Event'))
        self.model.setHeaderData(2, Qt.Orientation.Horizontal, self.tr('Information'))
        self.model.setHeaderData(3, Qt.Orientation.Horizontal, self.tr('Source'))
        self.model.setHeaderData(4, Qt.Orientation.Horizontal, self.tr('Time lost'))
        self.model.setHeaderData(5, Qt.Orientation.Horizontal, self.tr('Preview'))
        self.model.setHeaderData(6, Qt.Orientation.Horizontal, self.tr('Lost preview'))

    def _setup_filter(self):
        try:
            self.logger.debug("_setup_filter started")
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
            self.logger.debug("_setup_filter completed successfully")
            
        except Exception as e:
            self.logger.error(f"Error in _setup_filter: {e}", exc_info=True)
            raise

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
        if self.table:
            self.retrieve_data_signal.emit()
        show_event.accept()

    @pyqtSlot(QModelIndex)
    def _display_image(self, index):
        col = index.column()
        if col != 5 and col != 6:
            return

        path = index.data()
        if not path:
            return

        query = QSqlQuery(QSqlDatabase.database(self._db_connection_name))  # Getting a bounding_box of the current image
        if col == 5:
            query.prepare('SELECT bounding_box from objects WHERE preview_path = :path')
            query.bindValue(':path', path)
        else:
            query.prepare('SELECT lost_bounding_box from objects WHERE lost_preview_path = :path')
            query.bindValue(':path', path)
        if not query.exec():
            return
        if not query.next():
            return
        value = query.value(0)
        box = [0.0, 0.0, 0.0, 0.0]
        if value is not None:
            # Handle array returned as string "{a,b,c,d}" or as list/tuple
            try:
                if isinstance(value, str):
                    box_str = value.replace('{', '').replace('}', '')
                    box = [float(coord) for coord in box_str.split(',')]
                elif isinstance(value, (list, tuple)):
                    box = [float(v) for v in value]
                elif hasattr(value, 'toString'):
                    s = value.toString()
                    box_str = str(s).replace('{', '').replace('}', '')
                    box = [float(coord) for coord in box_str.split(',')]
                else:
                    s = str(value)
                    box_str = s.replace('{', '').replace('}', '')
                    parts = [p for p in box_str.split(',') if p.strip()]
                    if len(parts) == 4:
                        box = [float(coord) for coord in parts]
            except Exception:
                box = [0.0, 0.0, 0.0, 0.0]

        image_path = os.path.join(self.image_dir, path)
        previews_folder_path, file_name = os.path.split(image_path)
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
        if not self.isVisible() or not self._data_loaded or not self.model or not hasattr(self, '_db_connection_name'):
            return
        self.block_updates = True

        if camera_name == 'All':
            if (self.current_start_time == datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min) and
                    self.current_end_time == datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)):
                self.block_updates = False
            self._filter_records(self.current_start_time, self.current_end_time)
            return

        if camera_name not in self.source_name_id_address:
            return
        source_id, full_address = self.source_name_id_address[camera_name]
        # self.logger.debug(f"{camera_name}, {source_id}, {full_address}")
        query = QSqlQuery(QSqlDatabase.database(self._db_connection_name))
        query.prepare('SELECT time_stamp, CAST(\'ObjectEvent\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || ROUND(confidence::numeric, 2)'
                      ' AS information,'
                      'source_name, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE (time_stamp BETWEEN :start AND :finish) AND (source_id = :src_id) '
                      'AND (camera_full_address = :address) ORDER BY time_stamp DESC')
        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":src_id", source_id)
        query.bindValue(":address", full_address)
        query.exec()
        self.model.setQuery(query)

    def _filter_records(self, start_time, finish_time):
        if not self.model or not hasattr(self, '_db_connection_name'):
            return
        self.current_start_time = start_time
        self.current_end_time = finish_time
        query = QSqlQuery(QSqlDatabase.database(self._db_connection_name))
        query.prepare('SELECT time_stamp, CAST(\'ObjectEvent\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || ROUND(confidence::numeric, 2)'
                      ' AS information,'
                      'source_name, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC')
        query.bindValue(":start", start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", finish_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

    def _retrieve_data(self):
        if not self.isVisible() or not self._data_loaded or not self.model or not hasattr(self, 'filters'):
            return
        self.filters.setCurrentIndex(0)

        if not hasattr(self, '_db_connection_name'):
            return
            
        query = QSqlQuery(QSqlDatabase.database(self._db_connection_name))
        query.prepare('SELECT time_stamp, CAST(\'ObjectEvent\' AS text) AS event_type, '
                      '\'Object Id=\' || object_id || \'; class: \' || class_id || \'; conf: \' || ROUND(confidence::numeric, 2)'
                      ' AS information,'
                      'source_name, time_lost, preview_path, lost_preview_path FROM objects '
                      'WHERE time_stamp BETWEEN :start AND :finish ORDER BY time_stamp DESC')
        self.current_start_time = datetime.datetime.combine(datetime.datetime.now()-datetime.timedelta(days=1), datetime.time.min)
        self.current_end_time = datetime.datetime.combine(datetime.datetime.now(), datetime.time.max)
        # Сбрасываем дату в фильтрах
        if hasattr(self, 'start_time') and hasattr(self, 'finish_time'):
            self.start_time.setDateTime(
                QDateTime.fromString(self.current_start_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))
            self.finish_time.setDateTime(
                QDateTime.fromString(self.current_end_time.strftime("%H:%M:%S %d-%m-%Y"), "hh:mm:ss dd-MM-yyyy"))

        query.bindValue(":start", self.current_start_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.bindValue(":finish", self.current_end_time.strftime('%Y-%m-%d %H:%M:%S.%f'))
        query.exec()
        self.model.setQuery(query)

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

    def close(self):
        if self.db_controller:
            self._update_job_first_last_records()
        if hasattr(self, '_db_connection_name') and self._db_connection_name:
            QSqlDatabase.removeDatabase(self._db_connection_name)


    def _update_job_first_last_records(self):
        if not self.db_controller:
            return
        job_id = self.db_controller.get_job_id()
        update_query = ''
        data = None

        # Получаем номер последней записи в данном запуске
        last_obj_query = sql.SQL('''SELECT MAX(record_id) from objects WHERE job_id = %s''')
        records = self.db_controller.query(last_obj_query, (job_id,))
        if records:
            last_record = records[0][0]
            if not last_record:  # Обновляем информацию о последней записи, если записей не было, то -1
                update_query = sql.SQL('UPDATE jobs SET first_record = -1, last_record = -1 WHERE job_id = %s;')
                data = (job_id,)
            else:
                update_query = sql.SQL('UPDATE jobs SET last_record = %s WHERE job_id = %s;')
                data = (last_record, job_id)
        else:
            self.logger.warning(f"HandlerJournal._update_job_first_last_records: Database controller not returning data. Database may be closed.")

        self.db_controller.query(update_query, data)
