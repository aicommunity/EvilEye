"""
Унифицированный журнал событий, работающий с любым источником данных (БД или JSON)
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List, Tuple
import datetime

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QDateEdit
    from PyQt6.QtCore import Qt, QTimer, pyqtSlot, QDate
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton, QDateEdit
    from PyQt5.QtCore import Qt, QTimer, pyqtSlot, QDate
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source import EventJournalDataSource
from .unified_journal_components import UnifiedImageDelegate, UnifiedDateTimeDelegate, UnifiedImageWindow
from .unified_journal_base import UnifiedJournalBase
from ..core.logger import get_module_logger
import logging


class UnifiedEventsJournal(UnifiedJournalBase):
    """Унифицированный журнал событий, работающий с любым источником данных"""
    
    def __init__(self, data_source: EventJournalDataSource, base_dir: str = None,
                 parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        # Инициализировать базовый класс
        base_name = "evileye.unified_events_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        logger = parent_logger or logging.getLogger(full_name)
        super().__init__(data_source, base_dir, parent, full_name, logger)
        
        self.setWindowTitle('Events journal')
        self.resize(1600, 600)
        
        self.page = 0
        self.page_size = 50
        self.filters: Dict = {}
        
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
        self._is_closing = False
        
        # Scroll / update flags
        self._auto_scroll = True      # автопрокрутка, когда пользователь на новых событиях (вверху)
        self._updating_table = False  # защита от обработки скролла во время массовых обновлений
        
        # Real-time update timer (will be started in showEvent)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._check_for_updates)
        # Don't start timer here - will start when widget is shown
        
        # Image window reference
        self.image_win = None
        
        # Video player reference
        self.video_player = None
        
        # Initialize UI components (will be set in _build_ui)
        self.table = None
        self.date_edit = None
        self.btn_all_dates = None
        self.cmb_type = None
        
        self._build_ui()
        # Don't call _reload_table() here - will be called on first show
    
    def _get_source_name_from_address(self, camera_full_address: str) -> str:
        """Get source_name (camera name like Cam1, Cam2) from camera_full_address"""
        if not camera_full_address:
            return ''
        
        # Get source mappings from data_source
        source_mappings = getattr(self.data_source, '_source_name_id_address', {})
        if not source_mappings:
            return camera_full_address
        
        # Find source_name by matching camera_full_address
        for source_name, (source_id, address) in source_mappings.items():
            if address == camera_full_address:
                return source_name
        
        # If not found, return original address
        return camera_full_address

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

        # Event type filter
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(['All', 'attr_found', 'attr_lost', 'zone_entered', 'zone_left', 
                               'fov_found', 'fov_lost', 'cam', 'sys'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        self.layout.addLayout(toolbar)

        # Table with 6 columns: Time, Event, Information, Source, Time lost, Preview (with found/lost switching)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview'])
        h = self.table.horizontalHeader()
        v = self.table.verticalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Time
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Event
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Information
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Source
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Time lost
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Preview (with found/lost switching)
        h.setDefaultSectionSize(300)  # Set default size for image column
        v.setDefaultSectionSize(150)
        self.layout.addWidget(self.table)

        # Set up image delegate
        db_connection_name = getattr(self.data_source, 'db_connection_name', None)
        self.image_delegate = UnifiedImageDelegate(
            self.table, self.base_dir, db_connection_name,
            journal_type='events',
            journal_widget=self,
            logger_name="image_delegate", parent_logger=self.logger
        )
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview (with found/lost switching)

        # Set up datetime delegate
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

    def _on_filter_changed(self, text: str):
        """Handle filter change"""
        self.filters['event_type'] = None if text == 'All' else text
        self._reload_table()

    def _check_for_updates(self):
        """Check for data updates and refresh if needed"""
        try:
            if self._is_closing:
                return
            if self.table is None:
                return
            if self.data_source is None:
                return
            
            # Only update if widget is visible and data has been loaded
            if not self.is_visible or not self._data_loaded:
                return
            
            # Force refresh
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
            
            if not self._loaded_data:
                self._reload_table()
                return
            
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

    def _reload_table(self):
        """Reload table data from data source - initial load or full reload.
        Старательно сохраняем положение скролла, если пользователь читает старые записи.
        """
        # Флаг, что мы находимся в процессе массового обновления таблицы
        self._updating_table = True
        try:
            if self._is_closing:
                return
            if self.table is None:
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
                    
                    # Resolve video paths for events (always try if preview exists)
                    found_video_path = None
                    lost_video_path = None
                    if found_event and found_path:
                        found_video_path = self._resolve_video_path(found_event, found_path, is_lost=False)
                        if not found_video_path:
                            self.logger.warning(f"Preview found but video not found: found_preview={found_path}, event_type={found_event.get('event_type', '')}, source={found_event.get('source_name', '')}")
                    if lost_event and lost_path:
                        lost_video_path = self._resolve_video_path(lost_event, lost_path, is_lost=True)
                        if not lost_video_path:
                            self.logger.warning(f"Preview found but video not found: lost_preview={lost_path}, event_type={lost_event.get('event_type', '')}, source={lost_event.get('source_name', '')}")
                    
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
                        'found_video_path': found_video_path,
                        'lost_video_path': lost_video_path,
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
                                # (тот же якорь, что и в журнале объектов)
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
            self.logger.error(f"Table data loading error: {e}", exc_info=True)
        finally:
            self._updating_table = False

    def _build_table_rows(self, rows):
        """Построить список row_data из сырых событий."""
        from collections import defaultdict
        grouped = defaultdict(lambda: {'found': None, 'lost': None})
        cam_events = []
        sys_events = []
        
        for ev in rows:
            et = ev.get('event_type', '')
            if not et:
                continue
            
            if et == 'cam':
                cam_events.append(ev)
            elif et == 'sys':
                sys_events.append(ev)
            elif et.startswith('attr'):
                key = ('attr', ev.get('object_id'))
                if et == 'attr_found':
                    grouped[key]['found'] = ev
                elif et == 'attr_lost':
                    grouped[key]['lost'] = ev
            elif et.startswith('zone'):
                key = ('zone', ev.get('source_id'), ev.get('object_id'))
                if et == 'zone_entered':
                    grouped[key]['found'] = ev
                elif et == 'zone_left':
                    grouped[key]['lost'] = ev
            elif et.startswith('fov'):
                key = ('fov', ev.get('source_id'), ev.get('object_id'))
                if et == 'fov_found':
                    grouped[key]['found'] = ev
                elif et == 'fov_lost':
                    grouped[key]['lost'] = ev

        table_rows = []
        
        # Process grouped events
        for key, pair in grouped.items():
            kind = key[0]
            found_ev = pair['found']
            lost_ev = pair['lost']
            base = found_ev or lost_ev
            if not base:
                continue
            
            # Determine event name and information
            if kind == 'attr':
                event_name = 'AttributeEvent'
                info = f"AttributeEvent name={base.get('event_name', '')}; obj={base.get('object_id')}; class={base.get('class_name', base.get('class_id', ''))}; attrs={base.get('attrs', [])}"
            elif kind == 'zone':
                event_name = 'ZoneEvent'
                zone_id = base.get('zone_id')
                if zone_id is not None:
                    info = f"ZoneEvent obj={base.get('object_id')} zone={zone_id}"
                else:
                    info = f"ZoneEvent obj={base.get('object_id')}"
            else:  # fov
                event_name = 'FOVEvent'
                info = f"FOVEvent obj={base.get('object_id')}"

            row_data = {
                'source': base.get('source_name') or str(base.get('source_id', '')),
                'event': event_name,
                'information': info,
                'time': (found_ev.get('ts') if found_ev else base.get('ts', '')),
                'time_lost': (lost_ev.get('ts') if lost_ev else ''),
                'preview': (found_ev.get('image_filename', '') if found_ev else ''),
                'lost_preview': (lost_ev.get('image_filename', '') if lost_ev else ''),
                'found_event': found_ev,
                'lost_event': lost_ev
            }
            table_rows.append(row_data)

        # Add camera events as standalone rows
        for ev in cam_events:
            camera_full_address = ev.get('camera_full_address', '')
            source_name = self._get_source_name_from_address(camera_full_address)
            connection_status = ev.get('connection_status', False)
            status_text = 'reconnect' if connection_status else 'disconnect'
            table_rows.append({
                'source': source_name,
                'event': 'CameraEvent',
                'information': f"Camera={camera_full_address} {status_text}",
                'time': ev.get('ts', ''),
                'time_lost': '',
                'preview': '',
                'lost_preview': '',
                'found_event': None,
                'lost_event': None
            })

        # Add system events as standalone rows
        for ev in sys_events:
            system_event = ev.get('system_event', '')
            if system_event == 'SystemStart':
                information = 'System started'
            else:
                information = 'System stopped'
            table_rows.append({
                'source': 'System',
                'event': 'SystemEvent',
                'information': information,
                'time': ev.get('ts', ''),
                'time_lost': '',
                'preview': '',
                'lost_preview': '',
                'found_event': None,
                'lost_event': None
            })

        # Sort all rows by time desc
        try:
            table_rows.sort(key=lambda r: (r.get('time') or ''), reverse=True)
        except Exception:
            pass
        
        return table_rows

    
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
                threshold = max_value * 0.1
                self._auto_scroll = current_value <= threshold
        except Exception:
            pass
        
        # Load when reaching 80% of scroll
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
            
            # Filter and group events
            from collections import defaultdict
            grouped = defaultdict(lambda: {'found': None, 'lost': None})
            cam_events = []
            sys_events = []
            
            for ev in rows:
                et = ev.get('event_type', '')
                if not et:
                    continue
                
                if et == 'cam':
                    cam_events.append(ev)
                elif et == 'sys':
                    sys_events.append(ev)
                elif et.startswith('attr'):
                    key = ('attr', ev.get('object_id'))
                    if et == 'attr_found':
                        grouped[key]['found'] = ev
                    elif et == 'attr_lost':
                        grouped[key]['lost'] = ev
                elif et.startswith('zone'):
                    # zone_id doesn't exist in zone_events table, use source_id + object_id for grouping
                    key = ('zone', ev.get('source_id'), ev.get('object_id'))
                    if et == 'zone_entered':
                        grouped[key]['found'] = ev
                    elif et == 'zone_left':
                        grouped[key]['lost'] = ev
                elif et.startswith('fov'):
                    key = ('fov', ev.get('source_id'), ev.get('object_id'))
                    if et == 'fov_found':
                        grouped[key]['found'] = ev
                    elif et == 'fov_lost':
                        grouped[key]['lost'] = ev
            
            new_table_rows = []
            
            # Process grouped events
            for key, pair in grouped.items():
                kind = key[0]
                found_ev = pair['found']
                lost_ev = pair['lost']
                base = found_ev or lost_ev
                if not base:
                    continue
                
                # Determine event name and information
                if kind == 'attr':
                    event_name = 'AttributeEvent'
                    info = f"AttributeEvent name={base.get('event_name', '')}; obj={base.get('object_id')}; class={base.get('class_name', base.get('class_id', ''))}; attrs={base.get('attrs', [])}"
                elif kind == 'zone':
                    event_name = 'ZoneEvent'
                    # zone_id exists in JSON data but not in DB, so show it if available
                    zone_id = base.get('zone_id')
                    if zone_id is not None:
                        info = f"ZoneEvent obj={base.get('object_id')} zone={zone_id}"
                    else:
                        info = f"ZoneEvent obj={base.get('object_id')}"
                else:  # fov
                    event_name = 'FOVEvent'
                    info = f"FOVEvent obj={base.get('object_id')}"
                
                row_data = {
                    'source': base.get('source_name') or str(base.get('source_id', '')),
                    'event': event_name,
                    'information': info,
                    'time': (found_ev.get('ts') if found_ev else base.get('ts', '')),
                    'time_lost': (lost_ev.get('ts') if lost_ev else ''),
                    'preview': (found_ev.get('image_filename', '') if found_ev else ''),
                    'lost_preview': (lost_ev.get('image_filename', '') if lost_ev else ''),
                    'found_event': found_ev,
                    'lost_event': lost_ev
                }
                new_table_rows.append(row_data)
            
            # Add camera events
            for ev in cam_events:
                camera_full_address = ev.get('camera_full_address', '')
                source_name = self._get_source_name_from_address(camera_full_address)
                # Format information to match old journal: 'Camera=' || camera_full_address || ' ' || 'reconnect'/'disconnect'
                connection_status = ev.get('connection_status', False)
                status_text = 'reconnect' if connection_status else 'disconnect'
                new_table_rows.append({
                    'source': source_name,
                    'event': 'CameraEvent',
                    'information': f"Camera={camera_full_address} {status_text}",
                    'time': ev.get('ts', ''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })
            
            # Add system events
            for ev in sys_events:
                # Format information to match old journal: 'System started' or 'System stopped'
                system_event = ev.get('system_event', '')
                if system_event == 'SystemStart':
                    information = 'System started'
                else:
                    information = 'System stopped'
                new_table_rows.append({
                    'source': 'System',
                    'event': 'SystemEvent',
                    'information': information,
                    'time': ev.get('ts', ''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })
            
            # Sort new rows by time desc
            try:
                new_table_rows.sort(key=lambda r: (r.get('time') or ''), reverse=True)
            except Exception:
                pass
            
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
            for row_data in reversed(table_rows):
                self.table.insertRow(0)
                
                found_path = row_data.get('preview', '') or ''
                lost_path = row_data.get('lost_preview', '') or ''
                found_event = row_data.get('found_event')
                lost_event = row_data.get('lost_event')
                
                # Resolve video paths for events (always try if preview exists)
                found_video_path = None
                lost_video_path = None
                if found_event and found_path:
                    found_video_path = self._resolve_video_path(found_event, found_path, is_lost=False)
                    if not found_video_path:
                        self.logger.warning(f"Preview found but video not found: found_preview={found_path}, event_type={found_event.get('event_type', '')}, source={found_event.get('source_name', '')}")
                if lost_event and lost_path:
                    lost_video_path = self._resolve_video_path(lost_event, lost_path, is_lost=True)
                    if not lost_video_path:
                        self.logger.warning(f"Preview found but video not found: lost_preview={lost_path}, event_type={lost_event.get('event_type', '')}, source={lost_event.get('source_name', '')}")
                
                current_mode = 'found' if found_path else 'lost' if lost_path else 'found'
                default_path = lost_path if (current_mode == 'lost' and lost_path) else (found_path if found_path else lost_path)
                
                preview_item = QTableWidgetItem(default_path)
                preview_data = {
                    'found_path': found_path,
                    'lost_path': lost_path,
                    'found_event': found_event,
                    'lost_event': lost_event,
                    'found_video_path': found_video_path,
                    'lost_video_path': lost_video_path,
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
                    # Пользователь следит за новыми событиями - держим верх таблицы
                    scrollbar.setValue(scrollbar.minimum())
                elif anchor_key is not None:
                    try:
                        # Пользователь читает старые события: находим строку с тем же ключом и прокручиваем к ней
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
                
                # Resolve video paths for events (always try if preview exists)
                found_video_path = None
                lost_video_path = None
                if found_event and found_path:
                    found_video_path = self._resolve_video_path(found_event, found_path, is_lost=False)
                    if not found_video_path:
                        self.logger.warning(f"Preview found but video not found: found_preview={found_path}, event_type={found_event.get('event_type', '')}, source={found_event.get('source_name', '')}")
                if lost_event and lost_path:
                    lost_video_path = self._resolve_video_path(lost_event, lost_path, is_lost=True)
                    if not lost_video_path:
                        self.logger.warning(f"Preview found but video not found: lost_preview={lost_path}, event_type={lost_event.get('event_type', '')}, source={lost_event.get('source_name', '')}")
                
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
                    'found_video_path': found_video_path,
                    'lost_video_path': lost_video_path,
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
        """Display full image on double click"""
        if col != 5:  # Only Preview column (with found/lost switching)
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
                journal_type='events',
                base_dir=self.base_dir,
                data_source=self.data_source
            )
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
    
    def _parse_bbox_from_db(self, value) -> Optional[List[float]]:
        """Parse bounding box from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.replace('{', '').replace('}', '')
                parts = [p.strip() for p in s.split(',')]
                if len(parts) == 4:
                    return [float(p) for p in parts]
            elif isinstance(value, (list, tuple)):
                if len(value) == 4:
                    return [float(v) for v in value]
            elif hasattr(value, 'toString'):
                s = str(value.toString()).replace('{', '').replace('}', '')
                parts = [p.strip() for p in s.split(',')]
                if len(parts) == 4:
                    return [float(p) for p in parts]
        except Exception:
            pass
        return None
    
    def _parse_zone_coords_from_db(self, value) -> Optional[List[Tuple[float, float]]]:
        """Parse zone coordinates from database format"""
        if value is None:
            return None
        try:
            if isinstance(value, str):
                s = value.strip().strip('{}')
                points_str = [p.strip('{} ') for p in s.split('},')]
                coords = []
                for ps in points_str:
                    parts = [pp.strip() for pp in ps.split(',') if pp.strip()]
                    if len(parts) == 2:
                        coords.append((float(parts[0]), float(parts[1])))
                return coords if coords else None
            elif isinstance(value, (list, tuple)):
                return [(float(p[0]), float(p[1])) for p in value if isinstance(p, (list, tuple)) and len(p) == 2]
            elif hasattr(value, 'toString'):
                s = str(value.toString()).strip('{}')
                points_str = [p.strip('{} ') for p in s.split('},')]
                coords = []
                for ps in points_str:
                    parts = [pp.strip() for pp in ps.split(',') if pp.strip()]
                    if len(parts) == 2:
                        coords.append((float(parts[0]), float(parts[1])))
                return coords if coords else None
        except Exception:
            pass
        return None

    
    def _resolve_video_path(self, event_data: Optional[dict], preview_path: str = '', is_lost: bool = False) -> Optional[str]:
        """Resolve video fragment path for event with detailed logging
        
        Args:
            event_data: Event data dictionary from DB
            preview_path: Preview image path for logging
            is_lost: If True, look for lost video path, otherwise found video path
        
        Returns:
            Absolute path to video fragment, or None if not found
        """
        if not event_data or not self.base_dir:
            if preview_path:
                self.logger.debug(f"Video resolution skipped: event_data={event_data is not None}, base_dir={bool(self.base_dir)}, preview={preview_path}")
            return None
        
        # First, try to use saved video path from DB (preferred method)
        video_path_key = 'video_path_lost' if is_lost else 'video_path'
        saved_video_path = event_data.get(video_path_key)
        
        if saved_video_path:
            # Path from DB is relative to base_dir (e.g., "Events/2026-01-06/Videos/Cam1/Cam1_ZoneEvent_1762776230_20260106_001307.mp4")
            full_path = os.path.join(self.base_dir, saved_video_path)
            if os.path.exists(full_path):
                # Check file size - if too small, it might be corrupted
                try:
                    file_size = os.path.getsize(full_path)
                    if file_size < 1000:  # Less than 1KB - likely corrupted or empty
                        self.logger.warning(f"Saved video path from DB exists but is too small ({file_size} bytes): {full_path}, preview={preview_path}")
                        # Continue to fallback search
                    else:
                        self.logger.debug(f"Using saved video path from DB: {saved_video_path}, preview={preview_path}")
                        return full_path
                except Exception as e:
                    self.logger.warning(f"Error checking saved video file size: {e}, preview={preview_path}")
                    # Continue to fallback search
            else:
                self.logger.debug(f"Saved video path from DB does not exist (file may have been deleted): {full_path}, preview={preview_path}. Trying fallback search...")
        
        # Fallback to constructing path from event data (for backward compatibility)
        # Extract event info
        event_type = event_data.get('event_type', '')
        time_stamp = event_data.get('ts') or event_data.get('time_stamp')
        source_name = event_data.get('source_name', '')
        source_id = event_data.get('source_id')
        event_id_numeric = event_data.get('event_id_numeric')  # Numeric ID from DB
        event_id_str = event_data.get('event_id', '')
        
        if not all([event_type, time_stamp]):
            self.logger.debug(f"Video resolution skipped: missing required fields (event_type={bool(event_type)}, time_stamp={bool(time_stamp)}), preview={preview_path}")
            return None
        
        # Format timestamp
        if isinstance(time_stamp, datetime.datetime):
            date_folder = time_stamp.strftime('%Y-%m-%d')
            time_str = time_stamp.strftime('%Y%m%d_%H%M%S')
            time_str_partial = time_stamp.strftime('%Y%m%d_%H%M')  # For flexible matching (ignore seconds)
        elif isinstance(time_stamp, str):
            try:
                dt = datetime.datetime.fromisoformat(time_stamp.replace('Z', '+00:00'))
                date_folder = dt.strftime('%Y-%m-%d')
                time_str = dt.strftime('%Y%m%d_%H%M%S')
                time_str_partial = dt.strftime('%Y%m%d_%H%M')  # For flexible matching (ignore seconds)
            except Exception as e:
                self.logger.warning(f"Failed to parse timestamp '{time_stamp}' for video resolution: {e}, preview={preview_path}")
                return None
        else:
            self.logger.warning(f"Invalid timestamp type {type(time_stamp)} for video resolution, preview={preview_path}")
            return None
        
        # Map event_type to EventRecorder format
        event_name_map = {
            'zone_entered': 'ZoneEvent',
            'zone_left': 'ZoneEvent',
            'attr_found': 'AttributeEvent',
            'attr_lost': 'AttributeEvent',
            'fov_found': 'FOVEvent',
            'fov_lost': 'FOVEvent',
        }
        event_name = event_name_map.get(event_type, event_type)
        
        # Get possible camera folder names and source names
        # EventRecorder uses "-".join(source.source_names) for folder, but source_names[0] for filename
        possible_camera_folders = []
        possible_source_names = []
        
        # Get source mappings from data_source if available
        source_mappings = {}
        if hasattr(self.data_source, '_source_name_id_address'):
            source_mappings = self.data_source._source_name_id_address
        
        # If we have source_id, find all source_names that map to it
        if source_id is not None:
            for src_name, (src_id, address) in source_mappings.items():
                if src_id == source_id:
                    possible_source_names.append(src_name)
        
        # Also add source_name from event_data if available
        if source_name and source_name not in possible_source_names:
            possible_source_names.append(source_name)
        
        # If no source_names found, use source_name from event_data or empty
        if not possible_source_names:
            possible_source_names = [source_name] if source_name else []
        
        # Build possible camera folder names
        # EventRecorder creates folders using "-".join(source_names) for split sources
        # So we need to check all combinations
        if len(possible_source_names) > 1:
            # For split sources, try composite name
            possible_camera_folders.append("-".join(possible_source_names))
        # Also try individual source names
        for src_name in possible_source_names:
            if src_name not in possible_camera_folders:
                possible_camera_folders.append(src_name)
        
        # If no camera folders found, use source_name from event_data
        if not possible_camera_folders:
            possible_camera_folders = [source_name] if source_name else []
        
        # Try to find video file using numeric event_id (preferred method)
        videos_base_dir = os.path.join(self.base_dir, 'Events', date_folder, 'Videos')
        
        if event_id_numeric is not None and os.path.exists(videos_base_dir):
            # First, try exact match with possible folders and source names
            for camera_folder in possible_camera_folders:
                for src_name in possible_source_names:
                    # Format: {source_name}_{event_name}_{event_id}_{time_str}.mp4
                    video_path = os.path.join(
                        videos_base_dir, camera_folder,
                        f'{src_name}_{event_name}_{event_id_numeric}_{time_str}.mp4'
                    )
                    if os.path.exists(video_path):
                        self.logger.info(f"Found video fragment for event: type={event_type}, source={src_name}, camera_folder={camera_folder}, event_id={event_id_numeric}, time={time_str}, path={video_path}, preview={preview_path}")
                        return video_path
            
            # If not found, search all folders for files matching event_id and time
            try:
                for folder_name in os.listdir(videos_base_dir):
                    folder_path = os.path.join(videos_base_dir, folder_name)
                    if not os.path.isdir(folder_path):
                        continue
                    
                    # Look for file matching event_id and time_str
                    pattern = f'*_{event_name}_{event_id_numeric}_{time_str}.mp4'
                    import glob
                    matching_files = glob.glob(os.path.join(folder_path, pattern))
                    if matching_files:
                        video_path = matching_files[0]
                        self.logger.info(f"Found video fragment (searched all folders): type={event_type}, event_id={event_id_numeric}, time={time_str}, path={video_path}, preview={preview_path}")
                        return video_path
                    
                    # Also try with any event_id (event_id_numeric may not match real DB event_id)
                    # Look for files matching time_str and event_name
                    pattern_time = f'*_{event_name}_*_{time_str}.mp4'
                    matching_files = glob.glob(os.path.join(folder_path, pattern_time))
                    if matching_files:
                        # Prefer files with source_name in filename
                        for video_path in matching_files:
                            filename = os.path.basename(video_path)
                            # Check if any of possible_source_names is in filename
                            if any(src_name in filename for src_name in possible_source_names if src_name):
                                self.logger.info(f"Found video fragment (by time and source): type={event_type}, time={time_str}, path={video_path}, preview={preview_path}")
                                return video_path
                        # If no match by source_name, use first found
                        if matching_files:
                            video_path = matching_files[0]
                            self.logger.info(f"Found video fragment (by time only): type={event_type}, time={time_str}, path={video_path}, preview={preview_path}")
                            return video_path
            except Exception as e:
                self.logger.debug(f"Error searching all folders: {e}, preview={preview_path}")
        
        # Fallback: try without event_id (old format or if event_id_numeric not available)
        for camera_folder in possible_camera_folders:
            for src_name in possible_source_names:
                # Try format without event_id
                alt_path = os.path.join(
                    videos_base_dir, camera_folder,
                    f'{src_name}_{event_name}_{time_str}.mp4'
                )
                if os.path.exists(alt_path):
                    self.logger.info(f"Found video fragment (alt format) for event: type={event_type}, source={src_name}, camera_folder={camera_folder}, time={time_str}, path={alt_path}, preview={preview_path}")
                    return alt_path
        
        # Final fallback: search all folders for files matching time_str (most flexible)
        if os.path.exists(videos_base_dir):
            try:
                import glob
                # First, try exact time match
                pattern = f'*_{event_name}_*_{time_str}.mp4'
                all_matching = []
                for folder_name in os.listdir(videos_base_dir):
                    folder_path = os.path.join(videos_base_dir, folder_name)
                    if not os.path.isdir(folder_path):
                        continue
                    matching_files = glob.glob(os.path.join(folder_path, pattern))
                    all_matching.extend(matching_files)
                
                # If no exact match, try partial time match (ignore seconds) - allows for small time differences
                if not all_matching:
                    pattern_partial = f'*_{event_name}_*_{time_str_partial}*.mp4'
                    for folder_name in os.listdir(videos_base_dir):
                        folder_path = os.path.join(videos_base_dir, folder_name)
                        if not os.path.isdir(folder_path):
                            continue
                        matching_files = glob.glob(os.path.join(folder_path, pattern_partial))
                        all_matching.extend(matching_files)
                
                if all_matching:
                    # Prefer files with source_name in filename
                    for video_path in all_matching:
                        filename = os.path.basename(video_path)
                        if any(src_name in filename for src_name in possible_source_names if src_name):
                            self.logger.info(f"Found video fragment (final fallback by time and source): type={event_type}, time={time_str}, path={video_path}, preview={preview_path}")
                            return video_path
                    # If no match by source_name, use first found
                    video_path = all_matching[0]
                    self.logger.info(f"Found video fragment (final fallback by time only): type={event_type}, time={time_str}, path={video_path}, preview={preview_path}")
                    return video_path
            except Exception as e:
                self.logger.debug(f"Error in final fallback search: {e}, preview={preview_path}")
        
        # Log failure with details
        tried_paths = []
        if event_id_numeric is not None:
            for camera_folder in possible_camera_folders:
                for src_name in possible_source_names:
                    tried_paths.append(os.path.join(
                        self.base_dir, 'Events', date_folder, 'Videos', camera_folder,
                        f'{src_name}_{event_name}_{event_id_numeric}_{time_str}.mp4'
                    ))
        for camera_folder in possible_camera_folders:
            for src_name in possible_source_names:
                tried_paths.append(os.path.join(
                    self.base_dir, 'Events', date_folder, 'Videos', camera_folder,
                    f'{src_name}_{event_name}_{time_str}.mp4'
                ))
        
        self.logger.warning(
            f"No video fragment found for event: type={event_type}, source_name={source_name}, source_id={source_id}, "
            f"time={time_str}, event_id_numeric={event_id_numeric}, event_id_str={event_id_str}, date_folder={date_folder}, "
            f"possible_camera_folders={possible_camera_folders}, possible_source_names={possible_source_names}, "
            f"tried_paths={tried_paths[:5]}..., preview={preview_path}"
        )
        return None


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
            self.update_timer.start(1000)

    def hideEvent(self, event):
        """Handle hide event"""
        super().hideEvent(event)
        self.is_visible = False
        self.update_timer.stop()

    def closeEvent(self, event):
        """Handle close event"""
        self._is_closing = True
        self.update_timer.stop()
        if self.data_source:
            try:
                self.data_source.close()
            except Exception:
                pass
        super().closeEvent(event)
