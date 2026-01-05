"""
Унифицированный журнал событий, работающий с любым источником данных (БД или JSON)
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict, List

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
    from PyQt6.QtCore import Qt, QTimer, pyqtSlot
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox
    from PyQt5.QtCore import Qt, QTimer, pyqtSlot
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source import EventJournalDataSource
from .unified_journal_components import UnifiedImageDelegate, UnifiedDateTimeDelegate, UnifiedImageWindow
from ..core.logger import get_module_logger
import logging


class UnifiedEventsJournal(QWidget):
    """Унифицированный журнал событий, работающий с любым источником данных"""
    
    def __init__(self, data_source: EventJournalDataSource, base_dir: str = None,
                 parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.unified_events_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.setWindowTitle('Events journal')
        self.resize(1600, 600)
        
        self.data_source = data_source
        # Get base_dir from data_source if available
        if base_dir:
            self.base_dir = base_dir
        else:
            # Try to get from data_source attributes
            image_dir = getattr(data_source, 'image_dir', None)
            if image_dir:
                self.base_dir = image_dir
            else:
                base_dir_attr = getattr(data_source, 'base_dir', None)
                self.base_dir = base_dir_attr if base_dir_attr else ''
        
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
        
        # Cache for resolved image paths
        self._image_path_cache = {}
        self._is_closing = False
        
        # Cache for dates list
        self._dates_cache = None
        self._dates_loaded = False
        
        # Real-time update timer (will be started in showEvent)
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._check_for_updates)
        # Don't start timer here - will start when widget is shown
        
        # Image window reference
        self.image_win = None
        
        # Initialize UI components (will be set in _build_ui)
        self.table = None
        self.cmb_date = None
        self.cmb_type = None
        
        self._build_ui()
        # Don't call _reload_dates() here - will be called on first show
        # Don't call _reload_table() here - will be called on first show

    def _build_ui(self):
        """Build user interface"""
        self.layout = QVBoxLayout()

        toolbar = QHBoxLayout()

        # Date filter
        self.cmb_date = QComboBox()
        self.cmb_date.currentTextChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.cmb_date)

        # Event type filter
        self.cmb_type = QComboBox()
        self.cmb_type.addItems(['All', 'attr_found', 'attr_lost', 'zone_entered', 'zone_left', 
                               'fov_found', 'fov_lost', 'cam', 'sys'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        self.layout.addLayout(toolbar)

        # Table with 7 columns: Time, Event, Information, Source, Time lost, Preview, Lost preview
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview', 'Lost preview'])
        h = self.table.horizontalHeader()
        v = self.table.verticalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Time
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Event
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Information
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Source
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Time lost
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Preview
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Lost preview
        h.setDefaultSectionSize(300)
        v.setDefaultSectionSize(150)
        self.layout.addWidget(self.table)

        # Set up image delegate
        db_connection_name = getattr(self.data_source, 'db_connection_name', None)
        self.image_delegate = UnifiedImageDelegate(
            self.table, self.base_dir, db_connection_name,
            logger_name="image_delegate", parent_logger=self.logger
        )
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview
        self.table.setItemDelegateForColumn(6, self.image_delegate)  # Lost preview

        # Set up datetime delegate
        self.datetime_delegate = UnifiedDateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(4, self.datetime_delegate)  # Time lost

        # Connect double click signal
        self.table.cellDoubleClicked.connect(self._display_image)
        
        # Connect scroll handler for lazy loading
        self.table.verticalScrollBar().valueChanged.connect(self._on_scroll)

        self.setLayout(self.layout)

    def _reload_dates(self):
        """Reload available dates with caching"""
        try:
            # Use cached dates if available
            if self._dates_loaded and self._dates_cache is not None:
                dates = self._dates_cache
            else:
                # Load dates from data source
                dates = self.data_source.list_available_dates()
                self._dates_cache = dates
                self._dates_loaded = True
            
            self.cmb_date.clear()
            self.cmb_date.addItem('All')
            for d in dates:
                self.cmb_date.addItem(d)
        except Exception as e:
            self.logger.error(f"Date loading error: {e}")
            self.cmb_date.clear()
            self.cmb_date.addItem('All')

    def _on_date_changed(self, text: str):
        """Handle date selection change"""
        self.data_source.set_date(text if text and text != 'All' else None)
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
            self._reload_table()
        except Exception as e:
            self.logger.error(f"Update check error: {e}")

    def _reload_table(self):
        """Reload table data from data source - initial load or full reload"""
        try:
            if self._is_closing:
                return
            if self.table is None:
                return
            
            # Reset cache and page for full reload
            self._loaded_data = []
            self.page = 0
            # Reset initial load flag in data source
            if hasattr(self.data_source, '_is_initial_load'):
                self.data_source._is_initial_load = True
            
            filters = {k: v for k, v in self.filters.items() if v}
            rows = self.data_source.fetch(self.page, self.page_size, filters, [])
            
            # Filter and group events in one pass using defaultdict
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
                    key = ('zone', ev.get('source_id'), ev.get('zone_id'))
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
                    info = f"ZoneEvent obj={base.get('object_id')} zone={base.get('zone_id', '')}"
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
                table_rows.append({
                    'source': ev.get('camera_full_address', ''),
                    'event': 'CameraEvent',
                    'information': f"Camera {ev.get('camera_full_address')} status={ev.get('connection_status')}",
                    'time': ev.get('ts', ''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })

            # Add system events as standalone rows
            for ev in sys_events:
                table_rows.append({
                    'source': 'System',
                    'event': 'SystemEvent',
                    'information': f"System {ev.get('system_event', '')}",
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
            
            # Populate table - disable updates for performance
            self.table.setUpdatesEnabled(False)
            self.table.setSortingEnabled(False)
            try:
                # Set default row height once for all rows
                self.table.verticalHeader().setDefaultSectionSize(150)
                
                # Prepare all items first
                items_to_set = []
                for r, row_data in enumerate(table_rows):
                    # Preview column (5)
                    preview_path = self._resolve_image_path(row_data['preview'], row_data.get('found_event'))
                    preview_item = QTableWidgetItem(preview_path or '')
                    preview_item.setData(Qt.ItemDataRole.UserRole, row_data.get('found_event'))
                    
                    # Lost preview column (6)
                    lost_preview_path = self._resolve_image_path(row_data['lost_preview'], row_data.get('lost_event'))
                    lost_preview_item = QTableWidgetItem(lost_preview_path or '')
                    lost_preview_item.setData(Qt.ItemDataRole.UserRole, row_data.get('lost_event'))
                    
                    # Store all items for this row
                    row_items = [
                        QTableWidgetItem(str(row_data['time'])),  # Column 0
                        QTableWidgetItem(row_data['event']),  # Column 1
                        QTableWidgetItem(row_data['information']),  # Column 2
                        QTableWidgetItem(str(row_data.get('source', ''))),  # Column 3
                        QTableWidgetItem(str(row_data['time_lost'])),  # Column 4
                        preview_item,  # Column 5
                        lost_preview_item,  # Column 6
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
                
        except Exception as e:
            self.logger.error(f"Table data loading error: {e}", exc_info=True)
    
    def _on_scroll(self, value):
        """Handle scroll event - load next page when near bottom"""
        if self._is_loading:
            return
        
        scrollbar = self.table.verticalScrollBar()
        max_value = scrollbar.maximum()
        current_value = scrollbar.value()
        
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
                    key = ('zone', ev.get('source_id'), ev.get('zone_id'))
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
                    info = f"ZoneEvent obj={base.get('object_id')} zone={base.get('zone_id', '')}"
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
                new_table_rows.append({
                    'source': ev.get('camera_full_address', ''),
                    'event': 'CameraEvent',
                    'information': f"Camera {ev.get('camera_full_address')} status={ev.get('connection_status')}",
                    'time': ev.get('ts', ''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })
            
            # Add system events
            for ev in sys_events:
                new_table_rows.append({
                    'source': 'System',
                    'event': 'SystemEvent',
                    'information': f"System {ev.get('system_event', '')}",
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
                
                # Preview column (5)
                preview_path = self._resolve_image_path(row_data['preview'], row_data.get('found_event'))
                preview_item = QTableWidgetItem(preview_path or '')
                preview_item.setData(Qt.ItemDataRole.UserRole, row_data.get('found_event'))
                
                # Lost preview column (6)
                lost_preview_path = self._resolve_image_path(row_data['lost_preview'], row_data.get('lost_event'))
                lost_preview_item = QTableWidgetItem(lost_preview_path or '')
                lost_preview_item.setData(Qt.ItemDataRole.UserRole, row_data.get('lost_event'))
                
                # Set all items for this row
                self.table.setItem(row_idx, 0, QTableWidgetItem(str(row_data['time'])))
                self.table.setItem(row_idx, 1, QTableWidgetItem(row_data['event']))
                self.table.setItem(row_idx, 2, QTableWidgetItem(row_data['information']))
                self.table.setItem(row_idx, 3, QTableWidgetItem(str(row_data.get('source', ''))))
                self.table.setItem(row_idx, 4, QTableWidgetItem(str(row_data['time_lost'])))
                self.table.setItem(row_idx, 5, preview_item)
                self.table.setItem(row_idx, 6, lost_preview_item)
        finally:
            self.table.setSortingEnabled(True)
            self.table.setUpdatesEnabled(True)

    def _resolve_image_path(self, img_path: str, event_data: Optional[dict]) -> Optional[str]:
        """Resolve image path to full absolute path with caching"""
        if not img_path:
            return None
        
        # Create cache key including date_folder for proper caching
        cache_key = img_path
        if event_data:
            date_folder = event_data.get('date_folder', '')
            if date_folder:
                cache_key = f"{img_path}:{date_folder}"
        
        # Check cache first
        if cache_key in self._image_path_cache:
            cached_path = self._image_path_cache[cache_key]
            # Verify cached path still exists
            if cached_path and os.path.exists(cached_path):
                return cached_path
            # Remove invalid cache entry
            del self._image_path_cache[cache_key]
        
        # Already absolute
        if os.path.isabs(img_path):
            resolved = img_path if os.path.exists(img_path) else None
            self._image_path_cache[cache_key] = resolved
            return resolved
        
        # Try with base_dir
        resolved = None
        if self.base_dir:
            # Try direct path
            full_path = os.path.join(self.base_dir, img_path)
            if os.path.exists(full_path):
                resolved = full_path
            else:
                # Try with date_folder from event
                if event_data:
                    date_folder = event_data.get('date_folder', '')
                    if date_folder:
                        # New structure: Events/YYYY-MM-DD/Images/...
                        candidates = [
                            os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'FoundPreviews', os.path.basename(img_path)),
                            os.path.join(self.base_dir, 'Events', date_folder, 'Images', 'LostPreviews', os.path.basename(img_path)),
                            os.path.join(self.base_dir, 'images', date_folder, img_path),
                        ]
                        for cand in candidates:
                            if cand and os.path.exists(cand):
                                resolved = cand
                                break
                
                # Legacy paths
                if not resolved and (img_path.startswith('images' + os.sep) or img_path.startswith('images/')):
                    full_path = os.path.join(self.base_dir, img_path)
                    if os.path.exists(full_path):
                        resolved = full_path
        
        # Cache result
        self._image_path_cache[cache_key] = resolved
        return resolved

    @pyqtSlot(int, int)
    def _display_image(self, row, col):
        """Display full image on double click"""
        if col != 5 and col != 6:  # Only Preview and Lost preview columns
            return

        try:
            item = self.table.item(row, col)
            if not item:
                return
            
            img_path = item.text()
            if not img_path:
                return
            
            # Resolve full path
            event_data = item.data(Qt.ItemDataRole.UserRole)
            full_path = self._resolve_image_path(img_path, event_data)
            if not full_path or not os.path.exists(full_path):
                self.logger.warning(f"Image not found: {img_path}")
                return
            
            # Get bounding box and zone coords from event data
            box = None
            zone_coords = None
            if event_data:
                box = event_data.get('bounding_box') or event_data.get('box')
                zone_coords = event_data.get('zone_coords')
            
            # Try to resolve frame path
            frame_path = self._resolve_frame_path(full_path, event_data)
            if frame_path and os.path.exists(frame_path):
                full_path = frame_path
            
            # Normalize box if needed
            if box:
                box = self._normalize_bbox(box, full_path)
            
            # Pause auto updates
            self.update_timer.stop()
            
            # Close existing window
            if self.image_win:
                self.image_win.close()
            
            # Create and show image window
            self.image_win = UnifiedImageWindow(full_path, box, zone_coords)
            self.image_win.show()
            self.image_win.raise_()
            self.image_win.activateWindow()
            
            # Resume timer when window closed
            def _resume():
                self.update_timer.start(500)
            try:
                self.image_win.destroyed.connect(lambda *_: _resume())
            except Exception:
                pass
                
        except Exception as e:
            self.logger.error(f"Error displaying image: {e}", exc_info=True)

    def _resolve_frame_path(self, preview_path: str, event_data: Optional[dict]) -> Optional[str]:
        """Resolve preview path to full frame path"""
        if not preview_path or 'preview' not in preview_path.lower():
            return None
        
        # Replace preview with frame
        frame_path = preview_path.replace('previews', 'frames').replace('_preview.', '_frame.')
        frame_path = frame_path.replace('FoundPreviews', 'FoundFrames')
        frame_path = frame_path.replace('LostPreviews', 'LostFrames')
        
        if os.path.exists(frame_path):
            return frame_path
        
        return None

    def _normalize_bbox(self, box, img_path: str) -> Optional[list]:
        """Normalize bounding box to [x1, y1, x2, y2] format in [0,1] range"""
        if not box:
            return None
        
        try:
            from PyQt6.QtGui import QPixmap
        except ImportError:
            from PyQt5.QtGui import QPixmap
        
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return None
        
        img_w, img_h = pixmap.width(), pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return None
        
        try:
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return [x, y, x + w, y + h]
                else:
                    return [x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h]
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    return [a, b, c, d]
                else:
                    # Assume [x, y, w, h] in pixels
                    return [a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h]
        except Exception:
            pass
        
        return None

    def showEvent(self, event):
        """Handle show event - load data only on first show"""
        super().showEvent(event)
        
        # Note: isVisible() check removed - it can be False when switching tabs
        # even though the widget should be visible. showEvent is called when widget
        # should be shown, so we proceed with loading data.
        
        self.is_visible = True
        
        # Load dates on first show (if not already loaded)
        if not self._dates_loaded:
            self._reload_dates()
        
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
