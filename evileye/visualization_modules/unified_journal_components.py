"""
Унифицированные компоненты для журналов (делегаты, окна изображений)
Работают с любым источником данных (БД или JSON)
"""

import os
import datetime
from typing import Optional, List, Tuple

try:
    from PyQt6.QtCore import Qt, QSize, QPointF
    from PyQt6.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout
    from PyQt6.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import Qt, QSize, QPointF
    from PyQt5.QtWidgets import QStyledItemDelegate, QLabel, QVBoxLayout
    from PyQt5.QtGui import QPixmap, QPainter, QPen, QColor, QBrush, QPolygonF
    pyqt_version = 5

from ..core.logger import get_module_logger
import logging


class UnifiedImageDelegate(QStyledItemDelegate):
    """Универсальный делегат для отображения изображений в журналах"""
    
    def __init__(self, parent=None, base_dir=None, db_connection_name=None, 
                 logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        super().__init__(parent)
        base_name = "evileye.unified_image_delegate"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.base_dir = base_dir
        self.db_connection_name = db_connection_name
        self.preview_width = 300
        self.preview_height = 150

    def paint(self, painter, option, index):
        if not index.isValid():
            return
            
        # Get image path from index
        img_path = index.data(Qt.ItemDataRole.DisplayRole)
        if not img_path:
            return
        
        # Resolve full path
        full_path = self._resolve_image_path(img_path)
        if not full_path or not os.path.exists(full_path):
            return
            
        # Load image
        pixmap = QPixmap(full_path)
        if pixmap.isNull():
            return

        # Calculate target rect with aspect fit
        cell_rect = option.rect
        img_w = pixmap.width()
        img_h = pixmap.height()
        if img_w <= 0 or img_h <= 0:
            return
            
        cell_w = cell_rect.width()
        cell_h = cell_rect.height()
        scale = min(cell_w / img_w, cell_h / img_h)
        draw_w = int(img_w * scale)
        draw_h = int(img_h * scale)
        draw_x = cell_rect.x() + (cell_w - draw_w) // 2
        draw_y = cell_rect.y() + (cell_h - draw_h) // 2
        
        # Draw image
        painter.drawPixmap(draw_x, draw_y, draw_w, draw_h, pixmap)
        
        # Try to get bounding box and zone coords from event data
        event_data = index.data(Qt.ItemDataRole.UserRole)
        if event_data:
            self._draw_overlays(painter, event_data, draw_x, draw_y, draw_w, draw_h, full_path)
        elif self.db_connection_name:
            # Try to get from database
            self._draw_overlays_from_db(painter, img_path, draw_x, draw_y, draw_w, draw_h)

    def _resolve_image_path(self, img_path: str) -> Optional[str]:
        """Resolve image path to full absolute path"""
        if not img_path:
            return None
        
        # Already absolute
        if os.path.isabs(img_path):
            return img_path if os.path.exists(img_path) else None
        
        # Relative to base_dir
        if self.base_dir:
            full_path = os.path.join(self.base_dir, img_path)
            if os.path.exists(full_path):
                return full_path
            
            # Try with 'images' prefix
            if not img_path.startswith('images'):
                alt_path = os.path.join(self.base_dir, 'images', img_path)
                if os.path.exists(alt_path):
                    return alt_path
        
        return None

    def _draw_overlays(self, painter, event_data: dict, draw_x: int, draw_y: int, 
                      draw_w: int, draw_h: int, img_path: str):
        """Draw bounding box and zone overlays from event data"""
        # Draw bounding box
        box = event_data.get('bounding_box') or event_data.get('box')
        if box:
            painter.setPen(QPen(QColor(0, 255, 0), 2))  # Green for bbox
            
            # Normalize box coordinates
            x1, y1, x2, y2 = self._normalize_bbox(box, img_path)
            if x1 is not None:
                x = draw_x + int(x1 * draw_w)
                y = draw_y + int(y1 * draw_h)
                w = int((x2 - x1) * draw_w)
                h = int((y2 - y1) * draw_h)
                painter.drawRect(x, y, w, h)
        
        # Draw zone
        zone_coords = event_data.get('zone_coords')
        if zone_coords:
            painter.setPen(QPen(QColor(255, 0, 0), 2))  # Red for zone
            painter.setBrush(QBrush(QColor(255, 0, 0, 64)))  # Semi-transparent red fill
            polygon = QPolygonF()
            for pt in zone_coords:
                if isinstance(pt, (list, tuple)) and len(pt) == 2:
                    px, py = pt
                    x = draw_x + int(px * draw_w)
                    y = draw_y + int(py * draw_h)
                    polygon.append(QPointF(x, y))
            if polygon.count() > 0:
                painter.drawPolygon(polygon)

    def _draw_overlays_from_db(self, painter, img_path: str, draw_x: int, draw_y: int, 
                               draw_w: int, draw_h: int):
        """Try to get bounding box from database"""
        if not self.db_connection_name:
            return
        
        try:
            from PyQt6.QtSql import QSqlDatabase, QSqlQuery
        except ImportError:
            from PyQt5.QtSql import QSqlDatabase, QSqlQuery
        
        try:
            query = QSqlQuery(QSqlDatabase.database(self.db_connection_name))
            query.prepare('SELECT bounding_box FROM objects WHERE preview_path = :path OR lost_preview_path = :path LIMIT 1')
            query.bindValue(':path', img_path)
            if query.exec() and query.next():
                bbox_value = query.value(0)
                box = self._parse_bbox(bbox_value)
                if box:
                    x1, y1, x2, y2 = box
                    painter.setPen(QPen(QColor(0, 255, 0), 2))
                    x = draw_x + int(x1 * draw_w)
                    y = draw_y + int(y1 * draw_h)
                    w = int((x2 - x1) * draw_w)
                    h = int((y2 - y1) * draw_h)
                    painter.drawRect(x, y, w, h)
        except Exception:
            pass

    def _normalize_bbox(self, box, img_path: str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range"""
        if not box:
            return None, None, None, None
        
        try:
            # Handle different box formats
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    # Need to normalize
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                        return x / pixmap.width(), y / pixmap.height(), (x + w) / pixmap.width(), (y + h) / pixmap.height()
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    # Already normalized [x1, y1, x2, y2]
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    pixmap = QPixmap(img_path)
                    if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                        return a / pixmap.width(), b / pixmap.height(), (a + c) / pixmap.width(), (b + d) / pixmap.height()
        except Exception:
            pass
        
        return None, None, None, None

    def _parse_bbox(self, value) -> Optional[List[float]]:
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
        except Exception:
            pass
        return None

    def sizeHint(self, option, index) -> QSize:
        if index.isValid() and index.data(Qt.ItemDataRole.DisplayRole):
            return QSize(self.preview_width, self.preview_height)
        return super().sizeHint(option, index)


class UnifiedDateTimeDelegate(QStyledItemDelegate):
    """Универсальный делегат для отображения дат и времени"""
    
    def __init__(self, parent=None):
        super().__init__(parent)

    def displayText(self, value, locale) -> str:
        """Format datetime to show only seconds precision"""
        try:
            if isinstance(value, str):
                # Parse ISO format datetime string
                if 'T' in value:
                    # ISO format: 2025-09-01T17:30:45.123456
                    try:
                        dt = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
                        return dt.strftime('%Y-%m-%d %H:%M:%S')
                    except Exception:
                        return value
                else:
                    return value
            elif isinstance(value, datetime.datetime):
                return value.strftime('%Y-%m-%d %H:%M:%S')
            return str(value)
        except Exception as e:
            return str(value)


class UnifiedImageWindow(QLabel):
    """Универсальное окно для просмотра изображений с оверлеями"""
    
    def __init__(self, image_path: str, box=None, zone_coords=None, parent=None):
        super().__init__(parent)
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
            
            # Draw overlays
            if box:
                pen = QPen(QColor(0, 255, 0), 2)
                painter.setPen(pen)
                x1, y1, x2, y2 = self._normalize_bbox(box, pixmap)
                if x1 is not None:
                    x = draw_x + int(x1 * draw_w)
                    y = draw_y + int(y1 * draw_h)
                    w = int((x2 - x1) * draw_w)
                    h = int((y2 - y1) * draw_h)
                    painter.drawRect(x, y, w, h)
            
            if self.zone_coords:
                pen = QPen(QColor(255, 0, 0), 2)
                painter.setPen(pen)
                painter.setBrush(QBrush(QColor(255, 0, 0, 64)))
                polygon = QPolygonF()
                for pt in self.zone_coords:
                    if isinstance(pt, (list, tuple)) and len(pt) == 2:
                        px, py = pt
                        if max(px, py) <= 1.0:
                            x = draw_x + int(px * draw_w)
                            y = draw_y + int(py * draw_h)
                        else:
                            x = int(px)
                            y = int(py)
                        polygon.append(QPointF(x, y))
                if polygon.count() > 0:
                    painter.drawPolygon(polygon)
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

    def _normalize_bbox(self, box, pixmap: QPixmap) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Normalize bounding box to [0,1] range"""
        if not box:
            return None, None, None, None
        
        try:
            img_w, img_h = pixmap.width(), pixmap.height()
            if img_w <= 0 or img_h <= 0:
                return None, None, None, None
            
            if isinstance(box, dict):
                x = box.get('x', 0)
                y = box.get('y', 0)
                w = box.get('width', 0)
                h = box.get('height', 0)
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    return x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = box
                if max(a, b, c, d) <= 1.0:
                    return a, b, c, d
                else:
                    # Assume [x, y, w, h] in pixels
                    return a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h
        except Exception:
            pass
        
        return None, None, None, None

    def mouseDoubleClickEvent(self, event):
        self.hide()
        event.accept()
