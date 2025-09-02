import os
import json
import datetime
from typing import Dict, List

try:
    from PyQt6.QtCore import Qt, pyqtSlot
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QStyledItemDelegate
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush
    from PyQt6.QtCore import QSize, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt, pyqtSlot
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QStyledItemDelegate
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush
    from PyQt5.QtCore import QSize, QTimer
    pyqt_version = 5

from .journal_data_source_json import JsonLabelJournalDataSource


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, base_dir=None):
        super().__init__(parent)
        self.base_dir = base_dir
        self.preview_width = 300
        self.preview_height = 150

    def paint(self, painter, option, index):
        if not index.isValid():
            return
            
        # Get event data from the row
        table = self.parent()
        if not table:
            return
            
        row = index.row()
        if row >= table.rowCount():
            return
            
        # Get image filename from the row (Preview or Lost preview column)
        img_filename_item = table.item(row, index.column())  # Use current column
        
        if not img_filename_item:
            return
            
        img_path = img_filename_item.text()
        
        # If no image path, just return (empty cell)
        if not img_path:
            return
        
        # Use image path directly from JSON
        if not img_path:
            return
            
        if not os.path.exists(img_path):
            # Debug: print missing image path
            print(f"Image not found: {img_path}")
            return
            
        # Load and scale image
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
            
        pixmap = pixmap.scaled(self.preview_width, self.preview_height, 
                             Qt.AspectRatioMode.KeepAspectRatio, 
                             Qt.TransformationMode.SmoothTransformation)
        
        # Draw image only - no bounding boxes
        painter.drawPixmap(option.rect, pixmap)

    def sizeHint(self, option, index):
        return QSize(self.preview_width, self.preview_height)


class DateTimeDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        """Format datetime to show only seconds precision"""
        try:
            if isinstance(value, str):
                # Parse ISO format datetime string
                if 'T' in value:
                    # ISO format: 2025-09-01T17:30:45.123456
                    dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                    return dt.strftime('%Y-%m-%d %H:%M:%S')
                else:
                    # Already formatted or other format
                    return value
            return str(value)
        except Exception as e:
            print(f"Error formatting time: {e}")
            return str(value)


class ImageWindow(QLabel):
    def __init__(self, image_path, box=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Image')
        self.setFixedSize(900, 600)
        self.image_path = image_path
        
        # Load image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            print(f"Error loading image: {image_path}")
            return
            
        # Scale image to fit window
        pixmap = pixmap.scaled(self.width(), self.height(), 
                              Qt.AspectRatioMode.KeepAspectRatio, 
                              Qt.TransformationMode.SmoothTransformation)
        
        # Draw bounding box if provided
        if box:
            painter = QPainter(pixmap)
            pen = QPen(QColor(0, 255, 0), 2)  # Green color
            painter.setPen(pen)
            
            # Convert normalized coordinates to pixel coordinates
            x = int(box[0] * pixmap.width())
            y = int(box[1] * pixmap.height())
            w = int(box[2] * pixmap.width())
            h = int(box[3] * pixmap.height())
            
            painter.drawRect(x, y, w, h)
            painter.end()
        
        # Create label and set pixmap
        self.label = QLabel()
        self.label.setPixmap(pixmap)
        
        # Setup layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()


class EventsJournalJson(QWidget):
    def __init__(self, base_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Events journal (JSON)')
        self.base_dir = base_dir
        self.ds = JsonLabelJournalDataSource(base_dir)
        self.page = 0
        self.page_size = 50
        self.filters: Dict = {}
        
        # Store last data hash for efficient updates
        self.last_data_hash = None
        self.is_visible = False
        
        # Real-time update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._check_for_updates)
        self.update_timer.start(500)  # Check every 0.5 seconds for better responsiveness

        self._build_ui()
        self._reload_dates()
        self._reload_table()

    def _build_ui(self):
        self.layout = QVBoxLayout()

        toolbar = QHBoxLayout()
        # Remove the directory selection button - use base_dir directly
        # self.btn_open_dir = QPushButton('Open images dir')
        # self.btn_open_dir.clicked.connect(self._choose_dir)
        # toolbar.addWidget(self.btn_open_dir)

        self.cmb_date = QComboBox()
        self.cmb_date.currentTextChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.cmb_date)

        self.cmb_type = QComboBox()
        self.cmb_type.addItems(['All', 'found', 'lost'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        self.layout.addLayout(toolbar)

        # Use database journal structure: Name, Event, Information, Time, Time lost, Preview, Lost preview
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Name', 'Event', 'Information', 'Time', 'Time lost', 'Preview', 'Lost preview'])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        h.setDefaultSectionSize(300)  # Set default size for image columns
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns (Preview and Lost preview)
        self.image_delegate = ImageDelegate(self.table, self.base_dir)
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview
        self.table.setItemDelegateForColumn(6, self.image_delegate)  # Lost preview

        # Set up datetime delegate for time columns
        self.datetime_delegate = DateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(4, self.datetime_delegate)  # Time lost

        # Connect double click signal - use cellDoubleClicked for QTableWidget
        self.table.cellDoubleClicked.connect(self._display_image)
        
        # Store image window reference
        self.image_win = None

        self.setLayout(self.layout)
        
        # Enable automatic updates
        self.table.setUpdatesEnabled(True)
        
        # Connect show event to force update
        # Note: showEvent will be overridden in the class definition
        
        # Connect visibility change event (only if signal exists)
        try:
            self.visibilityChanged.connect(self._on_visibility_changed)
        except AttributeError:
            print("⚠️ visibilityChanged signal not available, skipping visibility tracking")
        
        # Connect focus change event for better responsiveness
        try:
            self.windowActivated.connect(self._on_window_activated)
        except AttributeError:
            print("⚠️ windowActivated signal not available, skipping activation tracking")

    def _choose_dir(self):
        d = QFileDialog.getExistingDirectory(self, 'Select images base directory', self.base_dir)
        if d:
            self.base_dir = d
            self.ds.set_base_dir(d)
            self._reload_dates()
            self._reload_table()

    def _on_date_changed(self, text: str):
        self.ds.set_date(text if text and text != 'All' else None)
        self._reload_table()

    def _on_filter_changed(self, text: str):
        self.filters['event_type'] = None if text == 'All' else text
        self._reload_table()

    def _reload_dates(self):
        try:
            dates = self.ds.list_available_dates()
            self.cmb_date.clear()
            self.cmb_date.addItem('All')
            for d in dates:
                self.cmb_date.addItem(d)
        except Exception as e:
            print(f"Error loading dates: {e}")
            self.cmb_date.clear()
            self.cmb_date.addItem('All')

    def _check_for_updates(self):
        """Check if data has changed and reload if necessary"""
        try:
            # Get current data hash
            filters = {k: v for k, v in self.filters.items() if v}
            current_data = self.ds.fetch(self.page, self.page_size, filters, [])
            
            # Create a hash based on data count and latest timestamp
            if current_data:
                latest_ts = max(ev.get('ts', '') for ev in current_data)
                data_count = len(current_data)
                current_hash = hash(f"{data_count}_{latest_ts}")
            else:
                current_hash = hash("empty")
            
            # Always reload for visible windows, or if data changed
            if current_hash != self.last_data_hash or self.is_visible:
                if current_hash != self.last_data_hash:
                    #print(f"🔄 Data changed! Hash: {self.last_data_hash} -> {current_hash}")
                    self.last_data_hash = current_hash
                #else:
                #    print(f"🔄 Forcing update for visible window. Hash: {current_hash}")
                
                self._reload_table()
                # Force widget repaint
                self.table.viewport().update()
                self.table.repaint()
        except Exception as e:
            print(f"❌ Error checking for updates: {e}")

    def _reload_table(self):
        try:
            filters = {k: v for k, v in self.filters.items() if v}
            # Use empty sort list to avoid sorting errors with None values
            rows = self.ds.fetch(self.page, self.page_size, filters, [])
            
            # Group events by object_id to show found and lost in same row
            grouped_events = {}
            for ev in rows:
                object_id = ev.get('object_id')
                if object_id not in grouped_events:
                    grouped_events[object_id] = {'found': None, 'lost': None}
                
                if ev.get('event_type') == 'found':
                    grouped_events[object_id]['found'] = ev
                elif ev.get('event_type') == 'lost':
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
                
                # Create row data
                row_data = {
                    'name': base_event.get('source_name', 'Unknown'),
                    'event': 'Event',  # Match database journal format
                    'information': f"Object Id={object_id}; class: {base_event.get('class_name', base_event.get('class_id', ''))}; conf: {base_event.get('confidence', 0):.2f}",
                    'time': found_event.get('ts') if found_event else (lost_event.get('ts') if lost_event else ''),
                    'time_lost': lost_event.get('ts') if lost_event else '',
                    'preview': found_event.get('image_filename') if found_event else '',
                    'lost_preview': lost_event.get('image_filename') if lost_event else '',
                    'found_event': found_event,
                    'lost_event': lost_event
                }
                table_rows.append(row_data)
            
            self.table.setRowCount(len(table_rows))
            for r, row_data in enumerate(table_rows):
                # Name column
                self.table.setItem(r, 0, QTableWidgetItem(row_data['name']))
                
                # Event column
                self.table.setItem(r, 1, QTableWidgetItem(row_data['event']))
                
                # Information column
                self.table.setItem(r, 2, QTableWidgetItem(row_data['information']))
                
                # Time column
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['time'])))
                
                # Time lost column
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['time_lost'])))
                
                # Preview column (found image)
                if row_data['preview']:
                    date_folder = row_data['found_event'].get('date_folder', '')
                    img_path = os.path.join(self.base_dir, 'images', date_folder, row_data['preview'])
                    item = QTableWidgetItem(img_path)
                    # Store event data for double click functionality
                    item.setData(Qt.ItemDataRole.UserRole, row_data['found_event'])
                    self.table.setItem(r, 5, item)
                else:
                    # Store empty string but still create item for delegate
                    item = QTableWidgetItem('')
                    self.table.setItem(r, 5, item)
                
                # Lost preview column
                if row_data['lost_preview']:
                    date_folder = row_data['lost_event'].get('date_folder', '')
                    img_path = os.path.join(self.base_dir, 'images', date_folder, row_data['lost_preview'])
                    item = QTableWidgetItem(img_path)
                    # Store event data for double click functionality
                    item.setData(Qt.ItemDataRole.UserRole, row_data['lost_event'])
                    self.table.setItem(r, 6, item)
                else:
                    # Store empty string but still create item for delegate
                    item = QTableWidgetItem('')
                    self.table.setItem(r, 6, item)
                
                # Set row height for image display
                self.table.setRowHeight(r, 150)
            
            # Force widget update to ensure changes are visible
            self.table.viewport().update()
            self.table.update()
            
            # Force repaint and process events
            self.table.repaint()
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        except Exception as e:
            print(f"Error loading table data: {e}")
    
    def _on_visibility_changed(self, visible):
        """Handle visibility change to force update when window becomes visible"""
        self.is_visible = visible
        if visible:
            print("🔄 Window became visible, forcing update...")
            self._reload_table()
    
    def force_update(self):
        """Force immediate update of the journal"""
        print("🔄 Force update requested...")
        self._reload_table()
        self.table.viewport().update()
        self.table.repaint()
    
    def _on_window_activated(self):
        """Handle window activation to force update"""
        print("🔄 Window activated, forcing update...")
        self._reload_table()
        self.table.viewport().update()
        self.table.repaint()

    def showEvent(self, event):
        """Start update timer when window is shown"""
        super().showEvent(event)
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()  # Stop first to ensure clean restart
            self.update_timer.start(1000)  # Restart timer every 1 second
        # Force immediate reload to show latest data
        self._reload_table()

    def hideEvent(self, event):
        """Stop update timer when window is hidden"""
        super().hideEvent(event)
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()

    def closeEvent(self, event):
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        self.ds.close()
        super().closeEvent(event)

    @pyqtSlot(int, int)
    def _display_image(self, row, col):
        """Display full image on double click (similar to database journal)"""
        if col != 5 and col != 6:  # Only Preview and Lost preview columns
            return

        # Get path from table item
        path = None
        table_item = self.table.item(row, col)
        if table_item:
            path = table_item.text()
        if not path:
            return

        # Get row data to find bounding box
        if row >= self.table.rowCount():
            return

        # Get event data from the row
        found_event = None
        lost_event = None
        
        # Try to get event data from table items (stored in UserRole)
        found_item = self.table.item(row, 5)  # Preview column
        lost_item = self.table.item(row, 6)    # Lost preview column
        
        if found_item:
            found_event = found_item.data(Qt.ItemDataRole.UserRole)
        if lost_item:
            lost_event = lost_item.data(Qt.ItemDataRole.UserRole)

        # Get bounding box from event data
        box = None
        if col == 5 and found_event:  # Preview column
            bbox_data = found_event.get('bounding_box')
            if bbox_data:
                if isinstance(bbox_data, dict):
                    # Convert dict format to list format
                    x = bbox_data.get('x', 0)
                    y = bbox_data.get('y', 0)
                    w = bbox_data.get('width', 0)
                    h = bbox_data.get('height', 0)
                    # Convert to normalized coordinates
                    if found_event.get('image_width') and found_event.get('image_height'):
                        img_w = found_event['image_width']
                        img_h = found_event['image_height']
                        box = [x / img_w, y / img_h, w / img_w, h / img_h]
                    else:
                        # Assume standard dimensions if not available
                        box = [x / 1920, y / 1080, w / 1920, h / 1080]
                elif isinstance(bbox_data, list) and len(bbox_data) == 4:
                    box = bbox_data
        elif col == 6 and lost_event:  # Lost preview column
            bbox_data = lost_event.get('bounding_box')
            if bbox_data:
                if isinstance(bbox_data, dict):
                    # Convert dict format to list format
                    x = bbox_data.get('x', 0)
                    y = bbox_data.get('y', 0)
                    w = bbox_data.get('width', 0)
                    h = bbox_data.get('height', 0)
                    # Convert to normalized coordinates
                    if lost_event.get('image_width') and lost_event.get('image_height'):
                        img_w = lost_event['image_width']
                        img_h = lost_event['image_height']
                        box = [x / img_w, y / img_h, w / img_w, h / img_h]
                    else:
                        # Assume standard dimensions if not available
                        box = [x / 1920, y / 1080, w / 1920, h / 1080]
                elif isinstance(bbox_data, list) and len(bbox_data) == 4:
                    box = bbox_data

        # Convert preview path to frame path (similar to database journal)
        image_path = path
        if 'preview' in path:
            # Extract filename and convert preview to frame
            dir_path, filename = os.path.split(path)
            if 'preview' in filename:
                # Replace 'preview' with 'frame' in filename
                new_filename = filename.replace('preview', 'frame')
                
                # Convert directory path from 'previews' to 'frames'
                if 'previews' in dir_path:
                    new_dir_path = dir_path.replace('previews', 'frames')
                    image_path = os.path.join(new_dir_path, new_filename)
                else:
                    # If no 'previews' in path, just replace filename
                    image_path = os.path.join(dir_path, new_filename)

        # Check if frame image exists, otherwise use preview
        if not os.path.exists(image_path):
            print(f"Frame image not found: {image_path}, using preview: {path}")
            image_path = path

        # Create and show image window
        self.image_win = ImageWindow(image_path, box)
        self.image_win.show()


