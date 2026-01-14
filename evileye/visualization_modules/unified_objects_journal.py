"""
Унифицированный журнал объектов, работающий с любым источником данных (БД или JSON)
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QDateEdit
    from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSlot, QDate
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QDateEdit
    from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSlot, QDate
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source import EventJournalDataSource
from .unified_journal_components import UnifiedImageDelegate, UnifiedDateTimeDelegate, UnifiedImageWindow
from .unified_journal_base import UnifiedJournalBase
from ..core.logger import get_module_logger
import logging


class UnifiedObjectsJournal(UnifiedJournalBase):
    """Унифицированный журнал объектов, работающий с любым источником данных"""
    
    def __init__(self, data_source: EventJournalDataSource, base_dir: str = None, 
                 parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        # Инициализировать базовый класс
        base_name = "evileye.unified_objects_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        logger = parent_logger or logging.getLogger(full_name)
        super().__init__(data_source, base_dir, parent, full_name, logger)
        
        self.setWindowTitle('Objects journal')
        self.resize(1600, 600)
        
        self.page = 0
        self.page_size = 50
        self.filters: dict = {}
        
        # Store last data hash for efficient updates
        self.last_data_hash = None
        self.is_visible = False
        
        # Flag to track if data has been loaded (lazy loading)
        self._data_loaded = False
        
        # Cache for loaded data and scroll loading
        self._loaded_data = []  # Cache of loaded data rows
        self._max_cache_size = 500  # Maximum cache size
        self._min_keep_size = 30  # Minimum records to keep (latest)
        self._is_loading = False  # Flag to prevent duplicate loading
        
        # Closing / scroll / update flags
        self._is_closing = False
        self._auto_scroll = True      # автопрокрутка, когда пользователь на новых событиях (вверху)
        self._updating_table = False  # защита от обработки скролла во время массовых обновлений
        
        # Real-time update timer (will be started in showEvent)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._check_for_updates)
        # Don't start timer here - will start when widget is shown
        
        # Image window reference
        self.image_win = None
        
        # Initialize UI components (will be set in _build_ui)
        self.table = None
        self.date_edit = None
        self.btn_all_dates = None
        self.cmb_type = None
        self.cmb_source = None
        
        self._build_ui()
        # Don't call _reload_table() here - will be called on first show

    def _build_ui(self):
        """Build user interface"""
        self.layout = QVBoxLayout()

        toolbar = QHBoxLayout()

        # Date filter with calendar
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setMinimumDate(QDate.currentDate().addDays(-365))
        self.date_edit.setMaximumDate(QDate.currentDate().addDays(365))
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.dateChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.date_edit)
        
        # Button to show all dates
        self.btn_all_dates = QPushButton("All")
        self.btn_all_dates.clicked.connect(self._on_all_dates_clicked)
        toolbar.addWidget(self.btn_all_dates)

        # Event type filter (found/lost)
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(['All', 'found', 'lost'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        # Source filter (if available)
        self.cmb_source = QComboBox()
        self.cmb_source.addItem('All')
        self.cmb_source.currentTextChanged.connect(self._on_source_changed)
        toolbar.addWidget(self.cmb_source)

        self.layout.addLayout(toolbar)

        # Table with 6 columns: Time, Event, Information, Source, Time lost, Preview (with found/lost switching)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview'])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Time
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Event
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Information
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Source
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Time lost
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Preview (with found/lost switching)
        h.setDefaultSectionSize(300)  # Set default size for image column
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns
        db_connection_name = getattr(self.data_source, 'db_connection_name', None)
        self.image_delegate = UnifiedImageDelegate(
            self.table, self.base_dir, db_connection_name,
            journal_type='objects',
            logger_name="image_delegate", parent_logger=self.logger
        )
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview (with found/lost switching)

        # Set up datetime delegate for time columns
        self.datetime_delegate = UnifiedDateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(4, self.datetime_delegate)  # Time lost

        # Connect double click signal
        self.table.cellDoubleClicked.connect(self._display_image)
        
        # Connect scroll handler for lazy loading
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.setLayout(self.layout)

    def _on_date_changed(self, date: QDate):
        """Handle date selection change"""
        date_str = date.toString('yyyy-MM-dd')
        self.data_source.set_date(date_str)
        self._reload_table()
    
    def _on_all_dates_clicked(self):
        """Handle 'All' button click - disable date filter"""
        self.data_source.set_date(None)
        self._reload_table()

    def _on_filter_changed(self, filter_text):
        """Handle event type filter change"""
        if filter_text == 'All':
            if 'event_type' in self.filters:
                del self.filters['event_type']
        else:
            self.filters['event_type'] = filter_text
        self._reload_table()

    def _on_source_changed(self, source_text):
        """Handle source filter change"""
        if source_text == 'All':
            if 'source_name' in self.filters:
                del self.filters['source_name']
        else:
            self.filters['source_name'] = source_text
        self._reload_table()

    def _check_for_updates(self):
        """Check for data updates and refresh if needed"""
        try:
            if self._is_closing or self.table is None or self.data_source is None:
                return
            # Only update if widget is visible and data has been loaded
            if not self.is_visible or not self._data_loaded:
                return
            
            # Force refresh of cache to get latest data
            try:
                self.data_source.force_refresh()
            except AttributeError:
                # Data source doesn't have force_refresh method
                pass

            # Инкрементальное обновление: получаем свежие данные первой страницы
            filters = {k: v for k, v in self.filters.items() if v}
            rows = self.data_source.fetch(0, self.page_size, filters, [])
            if not rows:
                return

            new_table_rows = self._build_table_rows(rows)
            if not new_table_rows:
                return

            # Если нет кэша — полный reload
            if not self._loaded_data:
                self._reload_table()
                return

            # Найдём, сколько верхних строк новые (сравниваем по ключу time+event+info)
            def make_key(row):
                return (row.get('time', ''), row.get('event', ''), row.get('information', ''))

            existing_keys = {make_key(r) for r in self._loaded_data[:max(1, len(new_table_rows))]}

            prepend_rows = []
            for r in new_table_rows:
                key = make_key(r)
                if key in existing_keys:
                    break
                prepend_rows.append(r)

            if not prepend_rows:
                return

            self._prepend_rows(prepend_rows)
        except Exception as e:
            self.logger.error(f"Update check error: {e}")

    def _build_table_rows(self, rows):
        """Построить список row_data из сырых событий."""
        from collections import defaultdict
        grouped_events = defaultdict(lambda: {'found': None, 'lost': None})
        for ev in rows:
            et = ev.get('event_type')
            if et not in ('found', 'lost'):
                continue
            object_id = ev.get('object_id')
            if et == 'found':
                grouped_events[object_id]['found'] = ev
            elif et == 'lost':
                grouped_events[object_id]['lost'] = ev
        
        table_rows = []
        for object_id, events in grouped_events.items():
            found_event = events['found']
            lost_event = events['lost']
            
            # Use found event as base, or lost event if no found event
            base_event = found_event or lost_event
            if not base_event:
                continue

            # Format information string
            object_id_val = base_event.get('object_id', '') or base_event.get('id', '') or ''
            class_name = base_event.get('class_name') or base_event.get('class_id', '') or base_event.get('class', '') or ''
            confidence = base_event.get('confidence') or base_event.get('conf', 0)
            if confidence is None:
                confidence = 0
            if isinstance(confidence, (int, float)):
                conf_str = f"{confidence:.2f}"
            else:
                conf_str = str(confidence) if confidence else '0.00'
            
            information = f"Object Id={object_id_val}; class: {class_name}; conf: {conf_str}"

            row_data = {
                'time': found_event.get('ts') if found_event else (lost_event.get('ts') if lost_event else ''),
                'event': 'ObjectEvent',
                'information': information,
                'source': base_event.get('source_name', ''),
                'time_lost': lost_event.get('ts') if lost_event else '',
                'preview': found_event.get('image_filename') if found_event else '',
                'lost_preview': lost_event.get('image_filename') if lost_event else '',
                'found_event': found_event,
                'lost_event': lost_event
            }
            table_rows.append(row_data)
        return table_rows

    def _reload_table(self):
        """Reload table data from data source - initial load or full reload.
        Старательно сохраняем положение скролла, если пользователь читает старые записи.
        """
        # Флаг, что мы находимся в процессе массового обновления таблицы
        self._updating_table = True
        try:
            if self._is_closing or self.table is None or self.data_source is None:
                return
            scrollbar = self.table.verticalScrollBar() if self.table is not None else None
            anchor_key = None
            restore_position = False
            
            # Если пользователь не в режиме авто-скролла, запомним «якорную» строку (верхнюю видимую)
            if scrollbar is not None and not self._auto_scroll and self.table.rowCount() > 0:
                try:
                    top_row = self.table.rowAt(0)
                    if top_row < 0:
                        top_row = 0
                    if 0 <= top_row < self.table.rowCount():
                        time_item = self.table.item(top_row, 0)
                        event_item = self.table.item(top_row, 1)
                        info_item = self.table.item(top_row, 2)
                        anchor_key = (
                            time_item.text() if time_item else '',
                            event_item.text() if event_item else '',
                            info_item.text() if info_item else '',
                        )
                        restore_position = True
                except Exception:
                    anchor_key = None
                    restore_position = False

            # Reset cache and page for full reload
            self._loaded_data = []
            self.page = 0
            # Reset initial load flag in data source
            if hasattr(self.data_source, '_is_initial_load'):
                self.data_source._is_initial_load = True
            
            filters = {k: v for k, v in self.filters.items() if v}
            rows = self.data_source.fetch(self.page, self.page_size, filters, [])
            
            # Build table rows
            table_rows = self._build_table_rows(rows)
            
            # Update source filter (temporarily disconnect signal to avoid recursion)
            sources = set()
            for row in table_rows:
                if row.get('source'):
                    sources.add(row['source'])
            
            # Only update combobox if sources changed
            current_items = set()
            for i in range(1, self.cmb_source.count()):  # Skip 'All' at index 0
                current_items.add(self.cmb_source.itemText(i))
            
            if sources != current_items:
                self.cmb_source.blockSignals(True)
                try:
                    current_text = self.cmb_source.currentText()
                    self.cmb_source.clear()
                    self.cmb_source.addItem('All')
                    if sources:
                        self.cmb_source.addItems(sorted(sources))
                    # Restore selection if it still exists
                    if current_text in sources or current_text == 'All':
                        self.cmb_source.setCurrentText(current_text)
                    else:
                        self.cmb_source.setCurrentText('All')
                finally:
                    self.cmb_source.blockSignals(False)
            
            # Populate table - disable updates for performance
            self.table.setUpdatesEnabled(False)
            self.table.setSortingEnabled(False)
            try:
                # Set default row height once for all rows
                self.table.verticalHeader().setDefaultSectionSize(150)
                
                # Prepare all items first
                items_to_set = []
                for r, row_data in enumerate(table_rows):
                    # Preview column (5) - combined found/lost preview with switching
                    found_path = row_data.get('preview', '') or ''
                    lost_path = row_data.get('lost_preview', '') or ''
                    found_event = row_data.get('found_event')
                    lost_event = row_data.get('lost_event')
                    
                    # Determine default path (prefer found, fallback to lost)
                    default_path = found_path if found_path else lost_path
                    current_mode = 'found' if found_path else 'lost' if lost_path else 'found'
                    
                    preview_item = QTableWidgetItem(default_path)
                    # Store both paths and events in UserRole for switching
                    preview_data = {
                        'found_path': found_path,
                        'lost_path': lost_path,
                        'found_event': found_event,
                        'lost_event': lost_event,
                        'current_mode': current_mode
                    }
                    preview_item.setData(Qt.ItemDataRole.UserRole, preview_data)
                    
                    # Store all items for this row
                    row_items = [
                        QTableWidgetItem(str(row_data['time'])),  # Column 0
                        QTableWidgetItem(row_data['event']),  # Column 1
                        QTableWidgetItem(row_data['information']),  # Column 2
                        QTableWidgetItem(str(row_data.get('source', ''))),  # Column 3
                        QTableWidgetItem(str(row_data.get('time_lost', '') or '')),  # Column 4
                        preview_item,  # Column 5 - combined preview with switching
                    ]
                    items_to_set.append(row_items)
                
                # Set row count and all items at once
                self.table.setRowCount(len(items_to_set))
                for r, row_items in enumerate(items_to_set):
                    for c, item in enumerate(row_items):
                        self.table.setItem(r, c, item)
                
                # Store loaded data in cache
                self._loaded_data = table_rows
            finally:
                # Re-enable updates and sorting
                self.table.setSortingEnabled(True)
                self.table.setUpdatesEnabled(True)
                
                # Восстановить положение скролла
                if scrollbar is not None:
                    try:
                        if self._auto_scroll and self.table.rowCount() > 0:
                            # Пользователь на новых событиях - держим верх таблицы
                            scrollbar.setValue(scrollbar.minimum())
                        elif restore_position and anchor_key is not None:
                            # Найдём строку с тем же ключом (time, event, info) и прокрутим к ней
                            target_row = None
                            for r in range(self.table.rowCount()):
                                t_item = self.table.item(r, 0)
                                e_item = self.table.item(r, 1)
                                i_item = self.table.item(r, 2)
                                key = (
                                    t_item.text() if t_item else '',
                                    e_item.text() if e_item else '',
                                    i_item.text() if i_item else '',
                                )
                                if key == anchor_key:
                                    target_row = r
                                    break
                            if target_row is not None:
                                self.table.scrollToItem(
                                    self.table.item(target_row, 0),
                                    QAbstractItemView.ScrollHint.PositionAtTop
                                )
                    except Exception:
                        pass
        except Exception as e:
            self.logger.error(f"Reload table error: {e}", exc_info=True)
        finally:
            self._updating_table = False
    
    def _on_scroll(self, value):
        """Handle scroll event - load next page when near bottom и обновить флаг авто-прокрутки"""
        if self._is_loading or self._updating_table:
            return
        
        scrollbar = self.table.verticalScrollBar()
        max_value = scrollbar.maximum()
        current_value = scrollbar.value()
        
        # Обновляем флаг auto-scroll: если пользователь близко к верху (новые события) - включаем,
        # если промотал вниз (старые события) - отключаем.
        try:
            if max_value <= 0:
                self._auto_scroll = True
            else:
                # порог ~ 10% от максимума
                threshold = max_value * 0.1
                self._auto_scroll = current_value <= threshold
        except Exception:
            pass
        
        # Load when reaching 80% of scroll (пагинация вниз)
        if max_value > 0 and max_value > 100:  # Only if there's significant scrolling
            scroll_percent = current_value / max_value if max_value > 0 else 0
            if scroll_percent > 0.8:
                self._load_next_page()
    
    def _load_next_page(self):
        """Load next page of data and append to table"""
        if self._is_loading:
            return
        
        self._is_loading = True
        try:
            self.page += 1
            filters = {k: v for k, v in self.filters.items() if v}
            rows = self.data_source.fetch(self.page, self.page_size, filters, [])
            
            if not rows:
                # No more data to load
                return
            
            # Filter and group events by object_id
            from collections import defaultdict
            grouped_events = defaultdict(lambda: {'found': None, 'lost': None})
            for ev in rows:
                et = ev.get('event_type')
                if et not in ('found', 'lost'):
                    continue
                object_id = ev.get('object_id')
                if et == 'found':
                    grouped_events[object_id]['found'] = ev
                elif et == 'lost':
                    grouped_events[object_id]['lost'] = ev
            
            # Create table rows from grouped events
            new_table_rows = []
            for object_id, events in grouped_events.items():
                found_event = events['found']
                lost_event = events['lost']
                
                base_event = found_event or lost_event
                if not base_event:
                    continue
                
                # Format information string
                object_id_val = base_event.get('object_id', '') or base_event.get('id', '') or ''
                class_name = base_event.get('class_name') or base_event.get('class_id', '') or base_event.get('class', '') or ''
                confidence = base_event.get('confidence') or base_event.get('conf', 0)
                if confidence is None:
                    confidence = 0
                if isinstance(confidence, (int, float)):
                    conf_str = f"{confidence:.2f}"
                else:
                    conf_str = str(confidence) if confidence else '0.00'
                
                information = f"Object Id={object_id_val}; class: {class_name}; conf: {conf_str}"
                
                row_data = {
                    'time': found_event.get('ts') if found_event else (lost_event.get('ts') if lost_event else ''),
                    'event': 'ObjectEvent',
                    'information': information,
                    'source': base_event.get('source_name', ''),
                    'time_lost': lost_event.get('ts') if lost_event else '',
                    'preview': found_event.get('image_filename') if found_event else '',
                    'lost_preview': lost_event.get('image_filename') if lost_event else '',
                    'found_event': found_event,
                    'lost_event': lost_event
                }
                new_table_rows.append(row_data)
            
            if new_table_rows:
                # Add to cache
                old_cache_size = len(self._loaded_data)
                self._loaded_data.extend(new_table_rows)
                
                # Manage cache size - keep latest _min_keep_size + new data
                if len(self._loaded_data) > self._max_cache_size:
                    keep_count = self._min_keep_size + len(new_table_rows)
                    if len(self._loaded_data) > keep_count:
                        # Calculate how many rows to remove
                        rows_to_remove = len(self._loaded_data) - keep_count
                        # Remove oldest entries from cache, keep latest
                        self._loaded_data = self._loaded_data[-keep_count:]
                        # Remove old rows from table (oldest first)
                        for _ in range(rows_to_remove):
                            if self.table.rowCount() > 0:
                                self.table.removeRow(0)
                
                # Append new rows to table
                self._append_to_table(new_table_rows)
        except Exception as e:
            self.logger.error(f"Load next page error: {e}", exc_info=True)
        finally:
            self._is_loading = False
    
    def _prepend_rows(self, table_rows):
        """Prepend new rows to the top of the table while preserving user scroll position when auto-scroll is off."""
        if not table_rows:
            return
        
        scrollbar = self.table.verticalScrollBar()
        # Запоминаем ключ верхней видимой строки (time, event, information) для точного восстановления позиции
        anchor_key = None
        if scrollbar is not None and not self._auto_scroll and self.table.rowCount() > 0:
            try:
                # Получаем индекс верхней видимой строки через viewport
                top_row = self.table.rowAt(0)
                if top_row < 0:
                    top_row = 0
                if 0 <= top_row < self.table.rowCount():
                    time_item = self.table.item(top_row, 0)
                    event_item = self.table.item(top_row, 1)
                    info_item = self.table.item(top_row, 2)
                    anchor_key = (
                        time_item.text() if time_item else '',
                        event_item.text() if event_item else '',
                        info_item.text() if info_item else '',
                    )
            except Exception:
                anchor_key = None

        self._updating_table = True
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        try:
            # Insert rows at top (from oldest to newest among prepend_rows to keep order)
            # table_rows assumed in time-desc order; we need to insert in reverse to keep final order
            for row_data in reversed(table_rows):
                self.table.insertRow(0)
                
                found_path = row_data.get('preview', '') or ''
                lost_path = row_data.get('lost_preview', '') or ''
                found_event = row_data.get('found_event')
                lost_event = row_data.get('lost_event')
                current_mode = 'found' if found_path else 'lost' if lost_path else 'found'
                default_path = lost_path if (current_mode == 'lost' and lost_path) else (found_path if found_path else lost_path)
                
                preview_item = QTableWidgetItem(default_path)
                preview_data = {
                    'found_path': found_path,
                    'lost_path': lost_path,
                    'found_event': found_event,
                    'lost_event': lost_event,
                    'current_mode': current_mode
                }
                preview_item.setData(Qt.ItemDataRole.UserRole, preview_data)
                
                self.table.setItem(0, 0, QTableWidgetItem(str(row_data['time'])))
                self.table.setItem(0, 1, QTableWidgetItem(row_data['event']))
                self.table.setItem(0, 2, QTableWidgetItem(row_data['information']))
                self.table.setItem(0, 3, QTableWidgetItem(str(row_data.get('source', ''))))
                self.table.setItem(0, 4, QTableWidgetItem(str(row_data.get('time_lost', '') or '')))
                self.table.setItem(0, 5, preview_item)
            
            # Update cache
            self._loaded_data = table_rows + self._loaded_data
            
            # Cache trimming if needed
            if len(self._loaded_data) > self._max_cache_size:
                self._loaded_data = self._loaded_data[:self._max_cache_size]
                # Remove extra rows from bottom
                while self.table.rowCount() > self._max_cache_size:
                    self.table.removeRow(self.table.rowCount() - 1)
            
            # Adjust scroll to preserve view if user is not on auto-scroll
            if scrollbar is not None:
                if self._auto_scroll:
                    # Пользователь следит за новыми сообщениями - держим верх таблицы
                    scrollbar.setValue(scrollbar.minimum())
                elif anchor_key is not None:
                    try:
                        # Пользователь читает старые сообщения: находим строку с тем же ключом и прокручиваем к ней
                        target_row = None
                        for r in range(self.table.rowCount()):
                            t_item = self.table.item(r, 0)
                            e_item = self.table.item(r, 1)
                            i_item = self.table.item(r, 2)
                            key = (
                                t_item.text() if t_item else '',
                                e_item.text() if e_item else '',
                                i_item.text() if i_item else '',
                            )
                            if key == anchor_key:
                                target_row = r
                                break
                        
                        if target_row is not None:
                            item = self.table.item(target_row, 0)
                            if item is not None:
                                try:
                                    from PyQt6.QtWidgets import QAbstractItemView
                                except ImportError:
                                    from PyQt5.QtWidgets import QAbstractItemView
                                self.table.scrollToItem(
                                    item,
                                    QAbstractItemView.ScrollHint.PositionAtTop
                                )
                    except Exception:
                        pass
        finally:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)
            self._updating_table = False

    def _append_to_table(self, table_rows):
        """Append new rows to the end of the table"""
        if not table_rows:
            return
        
        self.table.setUpdatesEnabled(False)
        self.table.setSortingEnabled(False)
        try:
            current_row_count = self.table.rowCount()
            self.table.setRowCount(current_row_count + len(table_rows))
            
            for r, row_data in enumerate(table_rows):
                row_idx = current_row_count + r
                
                # Preview column (5) - combined found/lost preview with switching
                found_path = row_data.get('preview', '') or ''
                lost_path = row_data.get('lost_preview', '') or ''
                found_event = row_data.get('found_event')
                lost_event = row_data.get('lost_event')
                
                # Determine default path (prefer found, fallback to lost)
                default_path = found_path if found_path else lost_path
                current_mode = 'found' if found_path else 'lost' if lost_path else 'found'
                
                preview_item = QTableWidgetItem(default_path)
                # Store both paths and events in UserRole for switching
                preview_data = {
                    'found_path': found_path,
                    'lost_path': lost_path,
                    'found_event': found_event,
                    'lost_event': lost_event,
                    'current_mode': current_mode
                }
                preview_item.setData(Qt.ItemDataRole.UserRole, preview_data)
                
                # Set all items for this row
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(row_data['time'])))
                self.table.setItem(row_idx, 1, QTableWidgetItem(row_data['event']))
                self.table.setItem(row_idx, 2, QTableWidgetItem(row_data['information']))
                self.table.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source', ''))))
                self.table.setItem(row_idx, 4, QTableWidgetItem(str(row_data.get('time_lost', '') or '')))
                self.table.setItem(row_idx, 5, preview_item)  # Combined preview with switching
        finally:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)


    @pyqtSlot(int, int)
    def _display_image(self, row, col):
        """Handle double click on image cell"""
        if col != 5:  # Only handle preview column (with found/lost switching)
            return

        try:
            item = self.table.item(row, col)
            if not item:
                return
            
            # Get preview data from UserRole (contains both found and lost paths)
            preview_data = item.data(Qt.ItemDataRole.UserRole)
            if not preview_data or not isinstance(preview_data, dict):
                return
            
            # Get found and lost events and paths
            found_path = preview_data.get('found_path', '')
            lost_path = preview_data.get('lost_path', '')
            found_event = preview_data.get('found_event')
            lost_event = preview_data.get('lost_event')
            
            if not found_path and not lost_path:
                return
            
            # Resolve full paths
            found_full_path = None
            lost_full_path = None
            
            if found_path:
                found_full_path = self._resolve_image_path(found_path, found_event)
                if found_full_path and os.path.exists(found_full_path):
                    # Try to resolve frame path (prefer full frame over preview)
                    frame_path = self._resolve_frame_path(found_full_path, found_event)
                    if frame_path and os.path.exists(frame_path):
                        found_full_path = frame_path
                else:
                    self.logger.warning(f"Found image not found: {found_path}")
                    found_full_path = None
            
            if lost_path:
                lost_full_path = self._resolve_image_path(lost_path, lost_event)
                if lost_full_path and os.path.exists(lost_full_path):
                    # Try to resolve frame path (prefer full frame over preview)
                    frame_path = self._resolve_frame_path(lost_full_path, lost_event)
                    if frame_path and os.path.exists(frame_path):
                        lost_full_path = frame_path
                else:
                    self.logger.warning(f"Lost image not found: {lost_path}")
                    lost_full_path = None
            
            if not found_full_path and not lost_full_path:
                return
            
            # Pause auto updates
            self.update_timer.stop()
            
            # Close existing window
            if self.image_win:
                self.image_win.close()
            
            # Create and show image window with tabs
            self.image_win = UnifiedImageWindow(
                found_image_path=found_full_path or '',
                found_event=found_event,
                lost_image_path=lost_full_path,
                lost_event=lost_event,
                journal_type='objects',
                base_dir=self.base_dir,
                data_source=self.data_source
            )
            
            # Add info to title
            if found_event:
                info_parts = []
                if found_event.get('object_id') is not None:
                    info_parts.append(f"obj={found_event['object_id']}")
                if found_event.get('class_name'):
                    info_parts.append(f"class={found_event['class_name']}")
                elif found_event.get('class_id'):
                    info_parts.append(f"class={found_event['class_id']}")
                if found_event.get('confidence') is not None:
                    conf = found_event['confidence']
                    if isinstance(conf, (int, float)):
                        info_parts.append(f"conf={conf:.2f}")
                    else:
                        info_parts.append(f"conf={conf}")
                if info_parts:
                    self.image_win.setWindowTitle('Media Viewer - ' + ' '.join(info_parts))
            
            self.image_win.show()
            self.image_win.raise_()
            self.image_win.activateWindow()
            
            # Resume timer when window closed
            def _resume():
                try:
                    # Проверяем, что таймер ещё существует и виджет не закрывается
                    if not self._is_closing and hasattr(self, 'update_timer') and self.update_timer is not None:
                        self.update_timer.start(500)
                except (RuntimeError, AttributeError):
                    # Таймер уже удалён Qt - игнорируем
                    pass
            try:
                self.image_win.destroyed.connect(lambda *_: _resume())
            except Exception:
                pass
                
        except Exception as e:
            self.logger.error(f"Error displaying image: {e}", exc_info=True)

    def showEvent(self, event):
        """Handle show event - load data only on first show"""
        super().showEvent(event)
        
        # Note: isVisible() check removed - it can be False when switching tabs
        # even though the widget should be visible. showEvent is called when widget
        # should be shown, so we proceed with loading data.
        
        self.is_visible = True
        
        # Load data only on first show (lazy loading)
        if not self._data_loaded:
            self._data_loaded = True
            self._reload_table()
        
        # Start update timer if not already active
        if not self.update_timer.isActive():
            self.update_timer.start(500)

    def hideEvent(self, event):
        """Handle hide event - stop update timer to save resources"""
        super().hideEvent(event)
        self.is_visible = False
        # Stop update timer when widget is hidden
        self.update_timer.stop()

    def closeEvent(self, event):
        """Handle close event - корректно останавливаем обновления и помечаем виджет как закрытый"""
        self._is_closing = True
        self.is_visible = False
        try:
            self.update_timer.stop()
        except Exception:
            pass
        if self.data_source:
            try:
                close_method = getattr(self.data_source, "close", None)
                if callable(close_method):
                    close_method()
            except Exception:
                pass
        super().closeEvent(event)