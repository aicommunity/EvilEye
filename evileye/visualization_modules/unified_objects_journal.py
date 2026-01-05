"""
Унифицированный журнал объектов, работающий с любым источником данных (БД или JSON)
"""

import os
import sys
from pathlib import Path
from typing import Optional

try:
    from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton
    from PyQt6.QtCore import Qt, QSize, QTimer, pyqtSlot
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton
    from PyQt5.QtCore import Qt, QSize, QTimer, pyqtSlot
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source import EventJournalDataSource
from .unified_journal_components import UnifiedImageDelegate, UnifiedDateTimeDelegate, UnifiedImageWindow
from ..core.logger import get_module_logger
import logging


class UnifiedObjectsJournal(QWidget):
    """Унифицированный журнал объектов, работающий с любым источником данных"""
    
    def __init__(self, data_source: EventJournalDataSource, base_dir: str = None, 
                 parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.unified_objects_journal"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.setWindowTitle('Objects journal')
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
        self.filters: dict = {}
        
        # Store last data hash for efficient updates
        self.last_data_hash = None
        self.is_visible = False
        
        # Flag to track if data has been loaded (lazy loading)
        self._data_loaded = False
        
        # Cache for resolved image paths
        self._image_path_cache = {}
        
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
        self.cmb_source = None
        
        self._build_ui()
        self._reload_dates()  # Load dates immediately (fast operation)
        # Don't call _reload_table() here - will be called on first show

    def _build_ui(self):
        """Build user interface"""
        self.layout = QVBoxLayout()

        toolbar = QHBoxLayout()

        # Date filter
        self.cmb_date = QComboBox()
        self.cmb_date.currentTextChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.cmb_date)

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

        # Table with 7 columns: Time, Event, Information, Source, Time lost, Preview, Lost preview
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Time', 'Event', 'Information', 'Source', 'Time lost', 'Preview', 'Lost preview'])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)  # Time
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)  # Event
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)  # Information
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)  # Source
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)  # Time lost
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)  # Preview
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)  # Lost preview
        h.setDefaultSectionSize(300)  # Set default size for image columns
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns
        db_connection_name = getattr(self.data_source, 'db_connection_name', None)
        self.image_delegate = UnifiedImageDelegate(
            self.table, self.base_dir, db_connection_name,
            logger_name="image_delegate", parent_logger=self.logger
        )
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview
        self.table.setItemDelegateForColumn(6, self.image_delegate)  # Lost preview

        # Set up datetime delegate for time columns
        self.datetime_delegate = UnifiedDateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(4, self.datetime_delegate)  # Time lost

        # Connect double click signal
        self.table.cellDoubleClicked.connect(self._display_image)

        self.setLayout(self.layout)

    def _reload_dates(self):
        """Reload available dates"""
        try:
            dates = self.data_source.list_available_dates()
            # Block signals to avoid triggering _on_date_changed during update
            self.cmb_date.blockSignals(True)
            try:
                self.cmb_date.clear()
                self.cmb_date.addItems(['All'] + dates)
                if dates:
                    self.cmb_date.setCurrentText(dates[-1])  # Select latest date
            finally:
                self.cmb_date.blockSignals(False)
        except Exception as e:
            self.logger.error(f"Error loading dates: {e}")
            self.cmb_date.blockSignals(True)
            try:
                self.cmb_date.clear()
                self.cmb_date.addItem('All')
            finally:
                self.cmb_date.blockSignals(False)

    def _on_date_changed(self, date_text):
        """Handle date selection change"""
        if date_text == 'All':
            self.data_source.set_date(None)
        else:
            self.data_source.set_date(date_text)
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
            # Only update if widget is visible and data has been loaded
            if not self.is_visible or not self._data_loaded:
                return
            
            # Force refresh of cache to get latest data
            try:
                self.data_source.force_refresh()
            except AttributeError:
                # Data source doesn't have force_refresh method
                pass
            self._reload_table()
        except Exception as e:
            self.logger.error(f"Update check error: {e}")

    def _reload_table(self):
        """Reload table data from data source"""
        try:
            filters = {k: v for k, v in self.filters.items() if v}
            rows = self.data_source.fetch(self.page, self.page_size, filters, [])
            
            # Filter and group events by object_id in one pass using defaultdict
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
            table_rows = []
            for object_id, events in grouped_events.items():
                found_event = events['found']
                lost_event = events['lost']
                
                # Use found event as base, or lost event if no found event
                base_event = found_event or lost_event
                if not base_event:
                    continue

                # Format information string
                object_id_val = base_event.get('object_id', '')
                class_name = base_event.get('class_name') or base_event.get('class_id', '')
                confidence = base_event.get('confidence', 0)
                if isinstance(confidence, (int, float)):
                    conf_str = f"{confidence:.2f}"
                else:
                    conf_str = str(confidence)
                
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
                    # Preview column (5) - found image
                    preview_path = self._resolve_image_path(row_data['preview'], row_data.get('found_event'))
                    preview_item = QTableWidgetItem(preview_path or '')
                    preview_item.setData(Qt.ItemDataRole.UserRole, row_data.get('found_event'))
                    
                    # Lost preview column (6) - lost image
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
            finally:
                # Re-enable updates and sorting
                self.table.setSortingEnabled(True)
                self.table.setUpdatesEnabled(True)
        except Exception as e:
            self.logger.error(f"Reload table error: {e}", exc_info=True)

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
                        # New structure: Detections/YYYY-MM-DD/Images/FoundPreviews or LostPreviews
                        candidates = [
                            os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'FoundPreviews', os.path.basename(img_path)),
                            os.path.join(self.base_dir, 'Detections', date_folder, 'Images', 'LostPreviews', os.path.basename(img_path)),
                            os.path.join(self.base_dir, 'images', date_folder, 'found_previews', os.path.basename(img_path)),
                            os.path.join(self.base_dir, 'images', date_folder, 'lost_previews', os.path.basename(img_path)),
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
        """Handle double click on image cell"""
        if col not in (5, 6):  # Only handle preview columns
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
            
            # Get bounding box from event data
            box = None
            if event_data:
                box = event_data.get('bounding_box') or event_data.get('box')
            
            # Try to resolve frame path (prefer full frame over preview)
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
            self.image_win = UnifiedImageWindow(full_path, box, None)
            
            # Add info to title
            if event_data:
                info_parts = []
                if event_data.get('object_id') is not None:
                    info_parts.append(f"obj={event_data['object_id']}")
                if event_data.get('class_name'):
                    info_parts.append(f"class={event_data['class_name']}")
                elif event_data.get('class_id'):
                    info_parts.append(f"class={event_data['class_id']}")
                if event_data.get('confidence') is not None:
                    conf = event_data['confidence']
                    if isinstance(conf, (int, float)):
                        info_parts.append(f"conf={conf:.2f}")
                    else:
                        info_parts.append(f"conf={conf}")
                if info_parts:
                    self.image_win.setWindowTitle('Image - ' + ' '.join(info_parts))
            
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
        frame_path = frame_path.replace('found_previews', 'found_frames')
        frame_path = frame_path.replace('lost_previews', 'lost_frames')
        
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