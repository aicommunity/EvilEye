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
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    from PyQt6.QtCore import QSize, QTimer, QPointF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt, pyqtSlot
    from PyQt5.QtWidgets import (
        QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton,
        QHeaderView, QComboBox, QTableWidget, QTableWidgetItem, QFileDialog, QStyledItemDelegate
    )
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    from PyQt5.QtCore import QSize, QTimer, QPointF
    pyqt_version = 5

from .journal_data_source_json import JsonLabelJournalDataSource
from ..core.logger import get_module_logger
import logging


class ImageDelegate(QStyledItemDelegate):
    def __init__(self, parent=None, base_dir=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.image_delegate"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
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
            self.logger.warning(f"Image not found: {img_path}")
            return
            
        # Load image
        pixmap = QPixmap(img_path)
        if pixmap.isNull():
            return

        # Compute target rect: STRETCH to full cell (match other tables)
        cell_rect = option.rect
        draw_x = cell_rect.x()
        draw_y = cell_rect.y()
        draw_w = cell_rect.width()
        draw_h = cell_rect.height()

        # Draw image stretched to cell rect
        painter.drawPixmap(cell_rect, pixmap)

        # Try to draw overlay box/zone for preview using target_rect as base
        ev_item = table.item(row, 5) if index.column() == 5 else table.item(row, 6)
        ev = ev_item.data(Qt.ItemDataRole.UserRole) if ev_item else None
        
        if ev:
            # Box - handle both dict and list formats
            box = ev.get('bounding_box') or ev.get('box')
            if box:
                painter.setPen(QPen(QColor(0, 255, 0), 2))  # Green for bbox

                # Extract corners
                if isinstance(box, dict):
                    x1 = box.get('x', 0)
                    y1 = box.get('y', 0)
                    w = box.get('width', 0)
                    h = box.get('height', 0)
                    x2 = x1 + w
                    y2 = y1 + h
                elif isinstance(box, (list, tuple)) and len(box) == 4:
                    x1, y1, x2, y2 = box
                else:
                    return

                # Normalize using full frame size when available
                if x1 > 1 or y1 > 1 or x2 > 1 or y2 > 1:
                    # Try to resolve corresponding full frame path
                    frame_path = None
                    try:
                        # Current cell path
                        img_filename_item = table.item(row, index.column())
                        cur_path = img_filename_item.text() if img_filename_item else ''
                        candidates = []
                        if cur_path:
                            candidates.append(cur_path.replace('previews', 'frames').replace('_preview.', '_frame.'))
                            candidates.append(cur_path.replace('/found_previews/', '/found_frames/').replace('_preview.', '_frame.'))
                            candidates.append(cur_path.replace('/lost_previews/', '/lost_frames/').replace('_preview.', '_frame.'))
                            candidates.append(cur_path.replace('detected_previews', 'found_frames').replace('_preview.', '_frame.'))
                        # Also try constructing from event date_folder
                        ev = table.item(row, 5).data(Qt.ItemDataRole.UserRole) if index.column() == 5 else table.item(row, 6).data(Qt.ItemDataRole.UserRole)
                        if ev:
                            date_folder = ev.get('date_folder', '')
                            base_name = os.path.basename(cur_path).replace('_preview.', '_frame.')
                            candidates.append(os.path.join(self.base_dir, 'images', date_folder, 'found_frames', base_name))
                            candidates.append(os.path.join(self.base_dir, 'images', date_folder, 'lost_frames', base_name))
                        for cand in candidates:
                            if cand and os.path.exists(cand):
                                frame_path = cand
                                break
                    except Exception:
                        frame_path = None

                    if frame_path:
                        fpix = QPixmap(frame_path)
                        if not fpix.isNull() and fpix.width() > 0 and fpix.height() > 0:
                            x1_norm = x1 / fpix.width()
                            y1_norm = y1 / fpix.height()
                            x2_norm = x2 / fpix.width()
                            y2_norm = y2 / fpix.height()
                        else:
                            # Fallback to preview size
                            x1_norm = x1 / pixmap.width()
                            y1_norm = y1 / pixmap.height()
                            x2_norm = x2 / pixmap.width()
                            y2_norm = y2 / pixmap.height()
                    else:
                        # Fallback to preview size
                        x1_norm = x1 / pixmap.width()
                        y1_norm = y1 / pixmap.height()
                        x2_norm = x2 / pixmap.width()
                        y2_norm = y2 / pixmap.height()
                else:
                    # Already normalized
                    x1_norm, y1_norm, x2_norm, y2_norm = x1, y1, x2, y2
                
                # Scale to draw area (full cell stretch)
                x = draw_x + int(x1_norm * draw_w)
                y = draw_y + int(y1_norm * draw_h)
                w = int((x2_norm - x1_norm) * draw_w)
                h = int((y2_norm - y1_norm) * draw_h)
                
                painter.drawRect(x, y, w, h)
            # Zone - use same logic as DB journal
            zc = ev.get('zone_coords')
            if zc and isinstance(zc, (list, tuple)):
                painter.setPen(QPen(QColor(255, 0, 0), 2))  # Red for zone
                painter.setBrush(QBrush(QColor(255, 0, 0, 64)))  # Semi-transparent red fill
                polygon = QPolygonF()
                for pt in zc:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        px, py = pt
                        # Scale to full cell area
                        x = draw_x + int(px * draw_w)
                        y = draw_y + int(py * draw_h)
                        polygon.append(QPointF(x, y))
                painter.drawPolygon(polygon)

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
            self.logger.error(f"Time formatting error: {e}")
            return str(value)


class ImageWindow(QLabel):
    def __init__(self, image_path, box=None, zone_coords=None, parent=None):
        super().__init__(parent)
        # Показывать как отдельное окно
        self.setWindowTitle('Image')
        try:
            self.setWindowFlag(Qt.Window, True)
            self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        except Exception:
            pass
        self.setFixedSize(900, 600)
        self.image_path = image_path
        self.zone_coords = zone_coords
        
        # Load image
        pixmap = QPixmap(image_path)
        if pixmap.isNull():
            try:
                self.logger.error(f"Image loading error: {image_path}")
            except Exception:
                pass
            # даже если не удалось загрузить, показываем окно с сообщением
            self.label = QLabel(f"Image not found:\n{image_path}")
            self.label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self.layout = QVBoxLayout()
            self.layout.addWidget(self.label)
            self.setLayout(self.layout)
            return
            
        # Compute target rect in window
        win_w, win_h = self.width(), self.height()
        img_w, img_h = pixmap.width(), pixmap.height()
        scale = min(win_w / img_w, win_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = (win_w - draw_w) // 2
        draw_y = (win_h - draw_h) // 2

        # Create canvas pixmap sized to window
        canvas = QPixmap(win_w, win_h)
        canvas.fill(QColor(0, 0, 0))
        painter = QPainter()
        try:
            painter.begin(canvas)
            # Draw image
            painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
            # Draw overlays in same mapping
            if box:
                pen = QPen(QColor(0, 255, 0), 2)
                painter.setPen(pen)
                # Поддержка dict {'x','y','width','height'}, [x,y,w,h] и [x1,y1,x2,y2]
                x1=y1=x2=y2=None
                if isinstance(box, dict):
                    bx = box.get('x', 0); by = box.get('y', 0); bw = box.get('width', 0); bh = box.get('height', 0)
                    if max(bx, by, bw, bh) <= 1.0:
                        x1 = bx; y1 = by; x2 = bx + bw; y2 = by + bh
                    else:
                        # абсолютные пиксели → нормализуем от размера исходного pixmap
                        x1 = bx / img_w; y1 = by / img_h; x2 = (bx + bw) / img_w; y2 = (by + bh) / img_h
                elif isinstance(box, (list, tuple)) and len(box) == 4:
                    a,b,c,d = box
                    if max(a,b,c,d) <= 1.0:
                        # это [x1,y1,x2,y2] в нормализованных координатах
                        x1,y1,x2,y2 = a,b,c,d
                    else:
                        # это [x,y,w,h] в пикселях
                        x1 = a / img_w; y1 = b / img_h; x2 = (a + c) / img_w; y2 = (b + d) / img_h
                if None not in (x1,y1,x2,y2):
                    x = draw_x + int(x1 * draw_w)
                    y = draw_y + int(y1 * draw_h)
                    w = int((x2 - x1) * draw_w)
                    h = int((y2 - y1) * draw_h)
                    painter.drawRect(x, y, w, h)
            if self.zone_coords:
                pen = QPen(QColor(255, 0, 0), 2)
                painter.setPen(pen)
                pts = []
                for px, py in self.zone_coords:
                    if max(px, py) <= 1.0:
                        pts.append((draw_x + int(px * draw_w), draw_y + int(py * draw_h)))
                    else:
                        pts.append((int(px), int(py)))
                for i in range(len(pts)):
                    x1, y1 = pts[i]
                    x2, y2 = pts[(i+1) % len(pts)]
                    painter.drawLine(x1, y1, x2, y2)
        finally:
            if painter.isActive():
                painter.end()
        
        # Create label and set pixmap
        self.label = QLabel()
        self.label.setPixmap(canvas)
        
        # Setup layout
        self.layout = QVBoxLayout()
        self.layout.addWidget(self.label)
        self.setLayout(self.layout)

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()


class EventsJournalJson(QWidget):
    def __init__(self, base_dir: str, parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.events_journal_json"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.setWindowTitle('Events journal (JSON)')
        self.resize(1600, 600)
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
        # Добавляем типы для атрибутных/зон/FOV событий, чтобы их можно было явно отфильтровать
        self.cmb_type.addItems(['All', 'found', 'lost', 'attr_found', 'attr_lost', 'zone_entered', 'zone_left', 'fov_found', 'fov_lost', 'cam'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        self.layout.addLayout(toolbar)

        # Use database journal structure: Time, Event, Event Details, Time lost, Information, Preview, Lost preview
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Time', 'Event', 'Event Details', 'Time lost', 'Information', 'Preview', 'Lost preview'])
        h = self.table.horizontalHeader()
        v = self.table.verticalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        # Match aspect ratio with other journals: width=300, height=150
        try:
            h.resizeSection(5, 300)
            h.resizeSection(6, 300)
        except Exception:
            pass
        try:
            v.setDefaultSectionSize(150)
        except Exception:
            pass
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns (Preview and Lost preview)
        self.image_delegate = ImageDelegate(self.table, self.base_dir, logger_name="image_delegate", parent_logger=self.logger)
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview
        self.table.setItemDelegateForColumn(6, self.image_delegate)  # Lost preview

        # Set up datetime delegate for time columns
        self.datetime_delegate = DateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(0, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(3, self.datetime_delegate)  # Time lost

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
            self.logger.warning("visibilityChanged signal unavailable, skipping visibility tracking")
        
        # Connect focus change event for better responsiveness
        try:
            self.windowActivated.connect(self._on_window_activated)
        except AttributeError:
            self.logger.warning("windowActivated signal unavailable, skipping activation tracking")

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
            self.logger.error(f"Date loading error: {e}")
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
                    #self.logger.debug(f"🔄 Data changed! Hash: {self.last_data_hash} -> {current_hash}")
                    self.last_data_hash = current_hash
                #else:
                #    self.logger.debug(f"🔄 Forcing update for visible window. Hash: {current_hash}")
                
                self._reload_table()
                # Force widget repaint
                self.table.viewport().update()
                self.table.repaint()
        except Exception as e:
            self.logger.error(f"Update check error: {e}")

    def _reload_table(self):
        try:
            filters = {k: v for k, v in self.filters.items() if v}
            # Use empty sort list to avoid sorting errors with None values
            rows = self.ds.fetch(self.page, self.page_size, filters, [])
            # Показываем события детекторов и системные: attr_*, zone_*, fov_*, cam, sys
            rows = [ev for ev in rows if (
                (et := ev.get('event_type', '')) and (
                    et.startswith('attr') or et.startswith('zone') or et.startswith('fov') or et == 'cam' or et == 'sys'
                )
            )]
            # Короткая сводка по типам для диагностики (в логи)
            try:
                counts = {}
                for ev in rows:
                    et = ev.get('event_type', 'na')
                    counts[et] = counts.get(et, 0) + 1
                self.logger.info(f"JSON events summary: {counts}")
            except Exception:
                pass
            
            # Group paired events to show both Preview and Lost preview in one row
            grouped = {}
            cam_events = []
            sys_events = []
            for ev in rows:
                et = ev.get('event_type','')
                if et.startswith('attr'):
                    key = ('attr', ev.get('object_id'))
                elif et.startswith('zone'):
                    key = ('zone', ev.get('source_id'), ev.get('zone_id'))
                elif et.startswith('fov'):
                    key = ('fov', ev.get('source_id'), ev.get('object_id'))
                elif et == 'cam':
                    cam_events.append(ev)
                    continue
                elif et == 'sys':
                    sys_events.append(ev)
                    continue
                else:
                    continue
                bucket = grouped.setdefault(key, {'found': None, 'lost': None})
                if et in ('attr_found','zone_entered','fov_found'):
                    bucket['found'] = ev
                elif et in ('attr_lost','zone_left','fov_lost'):
                    bucket['lost'] = ev

            table_rows = []
            for key, pair in grouped.items():
                kind = key[0]
                found_ev = pair['found']
                lost_ev = pair['lost']
                base = found_ev or lost_ev
                if not base:
                    continue
                if kind == 'attr':
                    event_name = 'AttributeEvent'
                    event_details = base.get('event_name','')
                    info = f"AttributeEvent name={base.get('event_name','')}; obj={base.get('object_id')}; class={base.get('class_name', base.get('class_id',''))}; attrs={base.get('attrs', [])}"
                elif kind == 'zone':
                    event_name = 'ZoneEvent'
                    event_details = str(base.get('source_id',''))
                    info = f"ZoneEvent obj={base.get('object_id')} zone={base.get('zone_id','')}"
                else:
                    event_name = 'FOVEvent'
                    event_details = str(base.get('source_id',''))
                    info = f"FOVEvent obj={base.get('object_id')}"

                row_data = {
                    'event': event_name,
                    'event_details': event_details,
                    'information': info,
                    'time': (found_ev.get('ts') if found_ev else base.get('ts','')),
                    'time_lost': (lost_ev.get('ts') if lost_ev else ''),
                    'preview': (found_ev.get('image_filename','') if found_ev else ''),
                    'lost_preview': (lost_ev.get('image_filename','') if lost_ev else ''),
                    'found_event': found_ev,
                    'lost_event': lost_ev
                }
                table_rows.append(row_data)

            # Add camera events as standalone rows
            for ev in cam_events:
                table_rows.append({
                    'event': 'CameraEvent',
                    'event_details': ev.get('camera_full_address',''),
                    'information': f"Camera {ev.get('camera_full_address')} status={ev.get('connection_status')}",
                    'time': ev.get('ts',''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })

            # Добавляем системные события отдельными строками
            for ev in sys_events:
                table_rows.append({
                    'event': 'SystemEvent',
                    'event_details': ev.get('system_event',''),
                    'information': f"System {ev.get('system_event','')}",
                    'time': ev.get('ts',''),
                    'time_lost': '',
                    'preview': '',
                    'lost_preview': '',
                    'found_event': None,
                    'lost_event': None
                })

            # Sort all rows by time desc to ensure recent System/Zone/etc are visible on first page
            try:
                table_rows.sort(key=lambda r: (r.get('time') or ''), reverse=True)
            except Exception:
                pass
            
            self.table.setRowCount(len(table_rows))
            for r, row_data in enumerate(table_rows):
                # Time column (0)
                self.table.setItem(r, 0, QTableWidgetItem(str(row_data['time'])))
                
                # Event column (1)
                self.table.setItem(r, 1, QTableWidgetItem(row_data['event']))
                
                # Event Details column (2)
                self.table.setItem(r, 2, QTableWidgetItem(row_data['event_details']))
                
                # Time lost column (3)
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['time_lost'])))
                
                # Information column (4)
                self.table.setItem(r, 4, QTableWidgetItem(row_data['information']))
                
                # Preview column (found image)
                if row_data['preview']:
                    date_folder = row_data['found_event'].get('date_folder', '')
                    prev = row_data['preview']
                    if os.path.isabs(prev):
                        img_path = prev
                    elif prev.startswith('images' + os.sep) or prev.startswith('images/'):
                        img_path = os.path.join(self.base_dir, prev)
                    else:
                        img_path = os.path.join(self.base_dir, 'images', date_folder, prev)
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
                    prev = row_data['lost_preview']
                    if os.path.isabs(prev):
                        img_path = prev
                    elif prev.startswith('images' + os.sep) or prev.startswith('images/'):
                        img_path = os.path.join(self.base_dir, prev)
                    else:
                        img_path = os.path.join(self.base_dir, 'images', date_folder, prev)
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
            try:
                from PyQt6.QtWidgets import QApplication
            except ImportError:
                from PyQt5.QtWidgets import QApplication
            QApplication.processEvents()
            
        except Exception as e:
            self.logger.error(f"Table data loading error: {e}")
    
    def _on_visibility_changed(self, visible):
        """Handle visibility change to force update when window becomes visible"""
        self.is_visible = visible
        if visible:
            self.logger.info("Window became visible, forced update...")
            self._reload_table()
    
    def force_update(self):
        """Force immediate update of the journal"""
        self.logger.info("Forced update requested...")
        self._reload_table()
        self.table.viewport().update()
        self.table.repaint()
    
    def _on_window_activated(self):
        """Handle window activation to force update"""
        self.logger.info("Window activated, forced update...")
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
                    box = [x, y, w, h]
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
                    box = [x, y, w, h]
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
            self.logger.warning(f"Frame image not found: {image_path}, using preview: {path}")
            image_path = path

        # Zone coords if present
        zone_coords = None
        if col == 5 and found_event and found_event.get('zone_coords'):
            zone_coords = found_event.get('zone_coords')
        elif col == 6 and lost_event and lost_event.get('zone_coords'):
            zone_coords = lost_event.get('zone_coords')

        # If box is in absolute pixels (>1), normalize using actual image size for correct scaling
        if box and max(box) > 1:
            try:
                from PyQt6.QtGui import QPixmap as _QPixmap
            except ImportError:
                from PyQt5.QtGui import QPixmap as _QPixmap
            pix = _QPixmap(image_path)
            if not pix.isNull() and pix.width() > 0 and pix.height() > 0:
                bx, by, bw, bh = box
                box = [bx / pix.width(), by / pix.height(), bw / pix.width(), bh / pix.height()]

        # Create and show image window
        self.image_win = ImageWindow(image_path, box, zone_coords)
        self.image_win.show()


