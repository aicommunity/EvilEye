import os
import sys
from pathlib import Path
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QComboBox, QPushButton
from PyQt6.QtCore import Qt, QSize, QTimer
from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
from PyQt6.QtCore import QPointF
from PyQt6.QtCore import pyqtSignal, pyqtSlot

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from . import events_journal_json
from . import handler_journal_view
from ..core.logger import get_module_logger
import logging


class ObjectsJournalJson(QWidget):
    """JSON-based objects journal that shows only object events (found/lost)."""
    
    def __init__(self, base_dir: str, parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.objects_journal_json"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.setWindowTitle('Objects journal (JSON)')
        self.resize(1600, 600)
        self.base_dir = base_dir
        
        # Use the same data source as events journal but filter for objects only
        self.ds = events_journal_json.JsonLabelJournalDataSource(base_dir)
        self.page = 0
        self.page_size = 50
        self.filters: dict = {}
        
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

        self.cmb_date = QComboBox()
        self.cmb_date.currentTextChanged.connect(self._on_date_changed)
        toolbar.addWidget(self.cmb_date)

        self.cmb_type = QComboBox()
        self.cmb_type.addItems(['All', 'found', 'lost'])
        self.cmb_type.currentTextChanged.connect(self._on_filter_changed)
        toolbar.addWidget(self.cmb_type)

        self.layout.addLayout(toolbar)

        # Use objects journal structure: Name, Event, Information, Time, Time lost, Preview, Lost preview
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(['Source', 'Event', 'Information', 'Time', 'Time lost', 'Preview', 'Lost preview'])
        h = self.table.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        h.setSectionResizeMode(5, QHeaderView.ResizeMode.Fixed)
        h.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        h.setDefaultSectionSize(300)  # Set default size for image columns
        self.layout.addWidget(self.table)

        # Set up image delegate for image columns (Preview and Lost preview)
        self.image_delegate = events_journal_json.ImageDelegate(self.table, self.base_dir, logger_name="image_delegate", parent_logger=self.logger)
        self.table.setItemDelegateForColumn(5, self.image_delegate)  # Preview
        self.table.setItemDelegateForColumn(6, self.image_delegate)  # Lost preview

        # Set up datetime delegate for time columns
        self.datetime_delegate = events_journal_json.DateTimeDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self.datetime_delegate)  # Time
        self.table.setItemDelegateForColumn(4, self.datetime_delegate)  # Time lost

        # Connect double click signal - use cellDoubleClicked for QTableWidget
        self.table.cellDoubleClicked.connect(self._display_image)
        
        # Store image window reference
        self.image_win = None

        self.setLayout(self.layout)

    def _reload_dates(self):
        """Reload available dates"""
        dates = self.ds.list_available_dates()
        self.cmb_date.clear()
        self.cmb_date.addItems(['All'] + dates)
        if dates:
            self.cmb_date.setCurrentText(dates[-1])  # Select latest date

    def _on_date_changed(self, date_text):
        """Handle date selection change"""
        if date_text == 'All':
            self.ds.set_date(None)
        else:
            self.ds.set_date(date_text)
        self._reload_table()

    def _on_filter_changed(self, filter_text):
        """Handle filter change"""
        if filter_text == 'All':
            self.filters = {}
        else:
            self.filters = {'event_type': filter_text}
        self._reload_table()

    def _check_for_updates(self):
        """Check for data updates and refresh if needed"""
        try:
            # Force refresh of cache to get latest data
            self.ds.force_refresh()
            self._reload_table()
        except Exception as e:
            self.logger.error(f"Update check error: {e}")

    def _reload_table(self):
        try:
            filters = {k: v for k, v in self.filters.items() if v}
            # Use empty sort list to avoid sorting errors with None values
            rows = self.ds.fetch(self.page, self.page_size, filters, [])
            
            # Filter for object events only (found/lost)
            object_events = [ev for ev in rows if ev.get('event_type') in ('found', 'lost')]
            
            # Group events by object_id to show found/lost in same row
            grouped_events = {}
            for ev in object_events:
                object_id = ev.get('object_id')
                if object_id not in grouped_events:
                    grouped_events[object_id] = {'found': None, 'lost': None}
                
                et = ev.get('event_type')
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

                row_data = {
                    'name': base_event.get('source_name', 'Unknown'),
                    'event': 'ObjectEvent',
                    'information': f"Object Id={base_event.get('object_id')}; class: {base_event.get('class_name', base_event.get('class_id',''))}; conf: {base_event.get('confidence', 0)}",
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
                # Name column (0)
                self.table.setItem(r, 0, QTableWidgetItem(row_data['name']))
                
                # Event column (1)
                self.table.setItem(r, 1, QTableWidgetItem(row_data['event']))
                
                # Information column (2)
                self.table.setItem(r, 2, QTableWidgetItem(row_data['information']))
                
                # Time column (3)
                self.table.setItem(r, 3, QTableWidgetItem(str(row_data['time'])))
                
                # Time lost column (4)
                self.table.setItem(r, 4, QTableWidgetItem(str(row_data['time_lost'])))
                
                # Preview column (5) - found image
                if row_data['preview']:
                    date_folder = row_data['found_event'].get('date_folder', '')
                    prev = row_data['preview']
                    if os.path.isabs(prev):
                        img_path = prev
                    elif prev.startswith('images' + os.sep) or prev.startswith('images/'):
                        img_path = os.path.join(self.base_dir, prev)
                    else:
                        img_path = os.path.join(self.base_dir, 'images', date_folder, prev)
                    # Fallbacks for unified folders and preview suffix
                    if not os.path.exists(img_path):
                        # replace legacy detected_frames -> found_previews and _frame -> _preview
                        alt1 = img_path.replace(os.path.join('images', date_folder, 'detected_frames'),
                                                os.path.join('images', date_folder, 'found_previews'))
                        alt1 = alt1.replace('_frame.', '_preview.')
                        if os.path.exists(alt1):
                            img_path = alt1
                        else:
                            # try found_frames (original frame) as last resort
                            alt2 = img_path.replace(os.path.join('images', date_folder, 'detected_frames'),
                                                    os.path.join('images', date_folder, 'found_frames'))
                            if os.path.exists(alt2):
                                img_path = alt2
                    item = QTableWidgetItem(img_path)
                    # Store event data for double click functionality
                    item.setData(Qt.ItemDataRole.UserRole, row_data['found_event'])
                    self.table.setItem(r, 5, item)
                else:
                    # Store empty string but still create item for delegate
                    item = QTableWidgetItem('')
                    item.setData(Qt.ItemDataRole.UserRole, row_data['found_event'])
                    self.table.setItem(r, 5, item)
                
                # Lost preview column (6) - lost image
                if row_data['lost_preview']:
                    date_folder = row_data['lost_event'].get('date_folder', '')
                    lost_prev = row_data['lost_preview']
                    if os.path.isabs(lost_prev):
                        img_path = lost_prev
                    elif lost_prev.startswith('images' + os.sep) or lost_prev.startswith('images/'):
                        img_path = os.path.join(self.base_dir, lost_prev)
                    else:
                        img_path = os.path.join(self.base_dir, 'images', date_folder, lost_prev)
                    # Fallbacks for unified folders and preview suffix
                    if not os.path.exists(img_path):
                        # replace legacy lost_frames -> lost_previews and _frame -> _preview
                        alt1 = img_path.replace(os.path.join('images', date_folder, 'lost_frames'),
                                                os.path.join('images', date_folder, 'lost_previews'))
                        alt1 = alt1.replace('_frame.', '_preview.')
                        if os.path.exists(alt1):
                            img_path = alt1
                    item = QTableWidgetItem(img_path)
                    # Store event data for double click functionality
                    item.setData(Qt.ItemDataRole.UserRole, row_data['lost_event'])
                    self.table.setItem(r, 6, item)
                else:
                    # Store empty string but still create item for delegate
                    item = QTableWidgetItem('')
                    item.setData(Qt.ItemDataRole.UserRole, row_data['lost_event'])
                    self.table.setItem(r, 6, item)
                
                # Set row height for image display
                self.table.setRowHeight(r, 150)
            
            # Force widget update to ensure changes are visible
            self.table.repaint()
        except Exception as e:
            self.logger.error(f"Reload table error: {e}")

    @pyqtSlot(int, int)
    def _display_image(self, row, col):
        """Handle double click on image cell"""
        try:
            self.logger.info(f"_display_image called: row={row} col={col}")
        except Exception:
            pass
        if col not in (5, 6):  # Only handle preview columns
            try:
                self.logger.info(f"_display_image ignored (not image column): row={row} col={col}")
            except Exception:
                pass
            return

        def _open():
            try:
                self.logger.info("_open: start")
                item = self.table.item(row, col)
                if not item:
                    self.logger.warning("_open: no item for cell")
                    return
                img_path = item.text()
                self.logger.info(f"_open: raw path={img_path}")
                if not img_path:
                    self.logger.warning("ImageWindow: empty image path")
                    return
                # resolve path
                if os.path.isabs(img_path):
                    img_path_abs = img_path
                else:
                    if img_path.startswith(self.base_dir + os.sep) or img_path.startswith(self.base_dir + '/'):
                        img_path_abs = img_path
                    elif img_path.startswith('images' + os.sep) or img_path.startswith('images/'):
                        img_path_abs = os.path.join(self.base_dir, img_path)
                    elif img_path.startswith(self.base_dir):
                        img_path_abs = img_path
                    else:
                        img_path_abs = os.path.join(self.base_dir, img_path)
                if not os.path.exists(img_path_abs):
                    ev = item.data(Qt.ItemDataRole.UserRole)
                    date_folder = ev.get('date_folder', '') if ev else ''
                    alt = os.path.join(self.base_dir, 'images', date_folder, os.path.basename(img_path))
                    self.logger.info(f"_open: resolved={img_path_abs}, alt={alt}")
                    if os.path.exists(alt):
                        img_path_abs = alt
                    else:
                        self.logger.warning(f"ImageWindow: image not found: {img_path} (checked {img_path_abs} and {alt})")
                        return
                # Prefer full frame over preview when possible
                try:
                    ev = item.data(Qt.ItemDataRole.UserRole)
                    date_folder = ev.get('date_folder', '') if ev else ''
                    dir_path, filename = os.path.split(img_path_abs)
                    candidates = []
                    # Simple replacements on current resolved path
                    candidates.append(img_path_abs.replace('previews', 'frames').replace('_preview.', '_frame.'))
                    # Unified folders replacements
                    candidates.append(img_path_abs.replace('/found_previews/', '/found_frames/').replace('_preview.', '_frame.'))
                    candidates.append(img_path_abs.replace('/lost_previews/', '/lost_frames/').replace('_preview.', '_frame.'))
                    # Legacy detected_previews to found_frames
                    candidates.append(img_path_abs.replace('detected_previews', 'found_frames').replace('_preview.', '_frame.'))
                    # Construct by date folder and base name
                    base_name = filename.replace('_preview.', '_frame.')
                    candidates.append(os.path.join(self.base_dir, 'images', date_folder, 'found_frames', base_name))
                    candidates.append(os.path.join(self.base_dir, 'images', date_folder, 'lost_frames', base_name))
                    for cand in candidates:
                        if cand and os.path.exists(cand):
                            img_path_abs = cand
                            break
                except Exception:
                    pass
                # Get event data for bounding box
                ev = item.data(Qt.ItemDataRole.UserRole)
                box = None
                if ev:
                    box = ev.get('bounding_box') or ev.get('box')
                self.logger.info(f"_open: using path={img_path_abs}; has_box={box is not None}")
                # pause auto updates to avoid UI contention
                try:
                    self.update_timer.stop()
                except Exception:
                    pass
                if hasattr(self, 'image_win') and self.image_win:
                    self.image_win.close()
                # Приводим box к формату [x1,y1,x2,y2] нормализованный
                norm_box = None
                if isinstance(box, dict):
                    bx = box.get('x',0); by = box.get('y',0); bw = box.get('width',0); bh = box.get('height',0)
                    if max(bx,by,bw,bh) <= 1.0:
                        norm_box = [bx,by,bx+bw,by+bh]
                    else:
                        # нормализуем по размеру исходного изображения
                        pm = QPixmap(img_path_abs)
                        iw, ih = pm.width(), pm.height()
                        if iw > 0 and ih > 0:
                            norm_box = [bx/iw, by/ih, (bx+bw)/iw, (by+bh)/ih]
                elif isinstance(box,(list,tuple)) and len(box)==4:
                    a,b,c,d = box
                    if max(a,b,c,d) <= 1.0:
                        norm_box = [a,b,c,d]
                    else:
                        pm = QPixmap(img_path_abs)
                        iw, ih = pm.width(), pm.height()
                        if iw > 0 and ih > 0:
                            # трактуем как [x,y,w,h] пиксели → нормализуем
                            norm_box = [a/iw, b/ih, (a+c)/iw, (b+d)/ih]
                self.logger.info(f"_open: norm_box={norm_box}")
                # Используем то же окно, что и в DB Objects журнале
                # ImageWindow ожидает box в формате [x1,y1,x2,y2]; при отсутствии bbox передаём нулевой прямоугольник
                safe_box = norm_box if norm_box is not None else [0.0, 0.0, 0.0, 0.0]
                # Создаём как отдельное окно (без родителя), чтобы были рамка и заголовок
                self.image_win = handler_journal_view.ImageWindow(img_path_abs, safe_box, None)
                # Добавим информационную подпись в заголовок (id/class/conf), как минимум текстом
                try:
                    info_title = []
                    if ev:
                        oid = ev.get('object_id'); cls = ev.get('class_name', ev.get('class_id',''))
                        conf = ev.get('confidence', None)
                        if oid is not None:
                            info_title.append(f"obj={oid}")
                        if cls not in (None, ''):
                            info_title.append(f"class={cls}")
                        if conf is not None:
                            info_title.append(f"conf={conf:.2f}" if isinstance(conf, (int,float)) else f"conf={conf}")
                    if info_title:
                        self.image_win.setWindowTitle('Image - ' + ' '.join(info_title))
                except Exception:
                    pass
                self.image_win.show()
                self.image_win.raise_()
                self.image_win.activateWindow()
                self.logger.info("_open: window shown")
                # resume timer when window closed
                def _resume():
                    try:
                        self.update_timer.start(500)
                    except Exception:
                        pass
                try:
                    self.image_win.destroyed.connect(lambda *_: _resume())
                except Exception:
                    pass
            except Exception as e:
                try:
                    self.logger.error(f"_open: exception: {e}")
                except Exception:
                    pass

        # Сразу пробуем открыть (чтобы исключить проблемы с очередью событий)
        try:
            self.logger.info("_display_image invoking open() synchronously")
        except Exception:
            pass
        _open()
        # Резервный отложенный вызов убран, чтобы не открывать окно дважды

    # Note: rely on cellDoubleClicked only to avoid signature mismatch warnings

    def showEvent(self, event):
        """Handle show event"""
        super().showEvent(event)
        self.is_visible = True
        self._reload_table()

    def hideEvent(self, event):
        """Handle hide event"""
        super().hideEvent(event)
        self.is_visible = False
