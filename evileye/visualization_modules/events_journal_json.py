import os
import json
from typing import Dict, List

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QStyledItemDelegate
    )
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush
    from PyQt6.QtCore import QSize, QTimer
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt
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


class EventsJournalJson(QWidget):
    def __init__(self, base_dir: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle('Events journal (JSON)')
        self.base_dir = base_dir
        self.ds = JsonLabelJournalDataSource(base_dir)
        self.page = 0
        self.page_size = 50
        self.filters: Dict = {}
        
        # Real-time update timer
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self._reload_table)
        self.update_timer.start(5000)  # Update every 5 seconds

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

        self.setLayout(self.layout)

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
                    self.table.setItem(r, 6, item)
                else:
                    # Store empty string but still create item for delegate
                    item = QTableWidgetItem('')
                    self.table.setItem(r, 6, item)
                
                # Set row height for image display
                self.table.setRowHeight(r, 150)
        except Exception as e:
            print(f"Error loading table data: {e}")
            self.table.setRowCount(0)

    def closeEvent(self, event):
        if hasattr(self, 'update_timer'):
            self.update_timer.stop()
        self.ds.close()
        super().closeEvent(event)


