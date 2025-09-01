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
    from PyQt6.QtCore import QSize
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QStyledItemDelegate
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush
    from PyQt5.QtCore import QSize
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
            
        # Get image filename and bounding box from the row
        img_filename_item = table.item(row, 4)  # Image column
        bbox_item = table.item(row, 5)  # BBox column
        
        if not img_filename_item or not bbox_item:
            return
            
        img_path = img_filename_item.text()
        bbox_text = bbox_item.text()
        
        # Use image path directly from JSON
        if not img_path or not os.path.exists(img_path):
            return
            
        # Load and scale image
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return
            
        pixmap = pixmap.scaled(self.preview_width, self.preview_height, 
                             Qt.AspectRatioMode.KeepAspectRatio, 
                             Qt.TransformationMode.SmoothTransformation)
        
        # Draw image
        painter.drawPixmap(option.rect, pixmap)
        
        # Parse and draw bounding box
        try:
            # Handle different bbox formats
            if bbox_text.startswith('[') and bbox_text.endswith(']'):
                # Array format: [x, y, width, height]
                bbox_values = json.loads(bbox_text)
                if len(bbox_values) == 4:
                    x, y, w, h = bbox_values
                else:
                    return
            else:
                # Try to parse as dict
                bbox = json.loads(bbox_text)
                if isinstance(bbox, dict) and 'x' in bbox and 'y' in bbox and 'width' in bbox and 'height' in bbox:
                    x = bbox['x']
                    y = bbox['y']
                    w = bbox['width']
                    h = bbox['height']
                else:
                    return
            
            # Calculate scaling factors (assuming original image dimensions)
            # For now, use simple scaling - in real implementation you'd need original image size
            scale_x = pixmap.width() / 1920  # Assuming 1920x1080 original
            scale_y = pixmap.height() / 1080
            
            # Draw bounding box
            pen = QPen(QColor(0, 255, 0), 2)  # Green color
            painter.setPen(pen)
            painter.setBrush(QBrush())
            
            x_scaled = int(x * scale_x)
            y_scaled = int(y * scale_y)
            w_scaled = int(w * scale_x)
            h_scaled = int(h * scale_y)
            
            painter.drawRect(x_scaled, y_scaled, w_scaled, h_scaled)
        except Exception as e:
            # print(f"Error drawing bbox: {e}")
            pass  # Ignore bbox parsing errors

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

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(['Type', 'Time', 'Source', 'Class', 'Image', 'BBox'])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        h.setDefaultSectionSize(300)  # Set default size for image columns
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns
        self.image_delegate = ImageDelegate(self.table, self.base_dir)
        self.table.setItemDelegateForColumn(4, self.image_delegate)
        self.table.setItemDelegateForColumn(5, self.image_delegate)

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
            rows = self.ds.fetch(self.page, self.page_size, filters, [('ts', 'desc')])
            self.table.setRowCount(len(rows))
            for r, ev in enumerate(rows):
                self.table.setItem(r, 0, QTableWidgetItem(ev.get('event_type') or ''))
                self.table.setItem(r, 1, QTableWidgetItem(ev.get('ts') or ''))
                self.table.setItem(r, 2, QTableWidgetItem(str(ev.get('source_name') or ev.get('source_id') or '')))
                self.table.setItem(r, 3, QTableWidgetItem(str(ev.get('class_name') or ev.get('class_id') or '')))
                
                # Image path and bounding box for delegate
                img_rel = ev.get('image_filename') or ''
                date_folder = ev.get('date_folder') or ''
                img_path = os.path.join(self.base_dir, 'images', date_folder, img_rel)
                self.table.setItem(r, 4, QTableWidgetItem(img_path))
                self.table.setItem(r, 5, QTableWidgetItem(str(ev.get('bounding_box') or '')))
                
                # Set row height for image display
                self.table.setRowHeight(r, 150)
        except Exception as e:
            print(f"Error loading table data: {e}")
            self.table.setRowCount(0)

    def closeEvent(self, event):
        self.ds.close()
        super().closeEvent(event)


