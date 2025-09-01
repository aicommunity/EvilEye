import os
from typing import Dict, List

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog
    )
    from PyQt6.QtGui import QPixmap
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog
    )
    from PyQt5.QtGui import QPixmap
    pyqt_version = 5

from .journal_data_source_json import JsonLabelJournalDataSource


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
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.layout.addWidget(self.table)

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
                # Image preview path
                img_rel = ev.get('image_filename') or ''
                date_folder = ev.get('date_folder') or ''
                img_path = os.path.join(self.base_dir, 'images', date_folder, img_rel)
                self.table.setItem(r, 4, QTableWidgetItem(img_path))
                self.table.setItem(r, 5, QTableWidgetItem(str(ev.get('bounding_box') or '')))
        except Exception as e:
            print(f"Error loading table data: {e}")
            self.table.setRowCount(0)

    def closeEvent(self, event):
        self.ds.close()
        super().closeEvent(event)


