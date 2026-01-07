"""
Виджет для отображения метаданных (объекты и события) поверх видео
"""

import os
import json
import datetime
from typing import Optional, List, Dict, Tuple

try:
    from PyQt6.QtWidgets import QWidget
    from PyQt6.QtCore import Qt, QPointF
    from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget
    from PyQt5.QtCore import Qt, QPointF
    from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QPolygonF
    pyqt_version = 5

from ..core.logger import get_module_logger
from .journal_metadata_extractor import EventMetadataExtractor


class MetadataOverlayWidget(QWidget):
    """Прозрачный виджет для отображения метаданных поверх видео"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.logger = get_module_logger("metadata_overlay")
        
        # Установить прозрачный фон
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet("background-color: transparent;")
        
        # Метаданные для отображения
        self._objects = []  # Список объектов
        self._events = []  # Список событий
        self._source_name = None  # Имя источника для фильтрации
        self._current_timestamp = None  # Текущий timestamp
        
        # Настройки отображения
        self._show_objects = True
        self._show_events = True
        self._show_labels = True
        
        # Размеры видео для нормализации координат
        self._video_width = 1920
        self._video_height = 1080
    
    def set_video_size(self, width: int, height: int):
        """Установить размеры видео для нормализации координат"""
        self._video_width = width
        self._video_height = height
    
    def load_metadata_for_time(self, timestamp: datetime.datetime, source_name: str, 
                               base_dir: str, date_folder: str):
        """Загрузить метаданные для указанного времени и источника"""
        self._current_timestamp = timestamp
        self._source_name = source_name
        
        self._objects = []
        self._events = []
        
        if not base_dir or not date_folder:
            return
        
        # Загрузить объекты из Detections
        detections_dir = os.path.join(base_dir, 'Detections', date_folder, 'Metadata')
        if os.path.exists(detections_dir):
            self._load_objects_from_json(detections_dir, timestamp, source_name)
        
        # Загрузить события из Events
        events_dir = os.path.join(base_dir, 'Events', date_folder, 'Metadata')
        if os.path.exists(events_dir):
            self._load_events_from_json(events_dir, timestamp, source_name)
        
        self.update()  # Обновить отрисовку
    
    def _load_objects_from_json(self, detections_dir: str, timestamp: datetime.datetime, source_name: str):
        """Загрузить объекты из JSON файлов"""
        files = ['objects_found.json', 'objects_lost.json']
        
        for filename in files:
            filepath = os.path.join(detections_dir, filename)
            if not os.path.exists(filepath):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                objects_list = data if isinstance(data, list) else data.get('objects', [])
                
                for obj in objects_list:
                    # Проверить соответствие времени и источника
                    obj_timestamp = self._parse_timestamp(obj.get('ts') or obj.get('time_stamp'))
                    obj_source = obj.get('source_name') or obj.get('source')
                    
                    if obj_timestamp and abs((obj_timestamp - timestamp).total_seconds()) < 1.0:
                        if obj_source == source_name or not source_name:
                            self._objects.append(obj)
            except Exception as e:
                self.logger.debug(f"Error loading objects from {filepath}: {e}")
    
    def _load_events_from_json(self, events_dir: str, timestamp: datetime.datetime, source_name: str):
        """Загрузить события из JSON файлов"""
        event_files = {
            'camera_events.json': 'camera_events',
            'system_events.json': 'system_events',
            'zone_events_entered.json': 'zone_events_entered',
            'zone_events_left.json': 'zone_events_left',
            'attribute_events_found.json': 'attribute_events_found',
            'attribute_events_finished.json': 'attribute_events_finished'
        }
        
        for filename, event_type in event_files.items():
            filepath = os.path.join(events_dir, filename)
            if not os.path.exists(filepath):
                continue
            
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                events_list = data if isinstance(data, list) else data.get('events', [])
                
                for event in events_list:
                    event['event_type'] = event_type
                    event_timestamp = self._parse_timestamp(event.get('ts') or event.get('time_stamp'))
                    event_source = event.get('source_name') or event.get('source')
                    
                    if event_timestamp and abs((event_timestamp - timestamp).total_seconds()) < 1.0:
                        if event_source == source_name or not source_name:
                            self._events.append(event)
            except Exception as e:
                self.logger.debug(f"Error loading events from {filepath}: {e}")
    
    def _parse_timestamp(self, ts_str: str) -> Optional[datetime.datetime]:
        """Распарсить timestamp из строки"""
        if not ts_str:
            return None
        
        try:
            # Попробовать различные форматы
            formats = [
                '%Y-%m-%d %H:%M:%S.%f',
                '%Y-%m-%d %H:%M:%S',
                '%Y-%m-%dT%H:%M:%S.%f',
                '%Y-%m-%dT%H:%M:%S'
            ]
            
            for fmt in formats:
                try:
                    return datetime.datetime.strptime(str(ts_str), fmt)
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def set_show_objects(self, show: bool):
        """Включить/выключить отображение объектов"""
        self._show_objects = show
        self.update()
    
    def set_show_events(self, show: bool):
        """Включить/выключить отображение событий"""
        self._show_events = show
        self.update()
    
    def set_show_labels(self, show: bool):
        """Включить/выключить отображение меток"""
        self._show_labels = show
        self.update()
    
    def paintEvent(self, event):
        """Отрисовать метаданные поверх видео"""
        super().paintEvent(event)
        
        if not self._show_objects and not self._show_events:
            return
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        widget_width = self.width()
        widget_height = self.height()
        
        if widget_width <= 0 or widget_height <= 0:
            return
        
        # Масштаб для преобразования координат видео в координаты виджета
        scale_x = widget_width / self._video_width if self._video_width > 0 else 1.0
        scale_y = widget_height / self._video_height if self._video_height > 0 else 1.0
        
        # Отрисовать объекты
        if self._show_objects:
            self._draw_objects(painter, scale_x, scale_y, widget_width, widget_height)
        
        # Отрисовать события
        if self._show_events:
            self._draw_events(painter, scale_x, scale_y, widget_width, widget_height)
        
        painter.end()
    
    def _draw_objects(self, painter: QPainter, scale_x: float, scale_y: float, 
                     widget_width: int, widget_height: int):
        """Отрисовать объекты"""
        for obj in self._objects:
            bbox = obj.get('bounding_box') or obj.get('box')
            if not bbox:
                continue
            
            # Нормализовать bbox
            norm_box = EventMetadataExtractor.normalize_bbox_for_display(
                bbox, self._video_width, self._video_height
            )
            
            if not norm_box:
                continue
            
            # Отрисовать прямоугольник
            x1, y1, x2, y2 = norm_box
            x = int(x1 * widget_width)
            y = int(y1 * widget_height)
            w = int((x2 - x1) * widget_width)
            h = int((y2 - y1) * widget_height)
            
            # Зеленый цвет для объектов
            painter.setPen(QPen(QColor(0, 255, 0), 2))
            painter.drawRect(x, y, w, h)
            
            # Отрисовать метку если включено
            if self._show_labels:
                class_id = obj.get('class_id', '?')
                confidence = obj.get('confidence', 0.0)
                label_text = f"Class:{class_id} {confidence:.2f}"
                
                painter.setPen(QPen(QColor(0, 255, 0), 1))
                painter.setBrush(QBrush(QColor(0, 0, 0, 180)))
                painter.drawRect(x, y - 20, len(label_text) * 7, 20)
                painter.setPen(QPen(QColor(255, 255, 255), 1))
                painter.drawText(x + 5, y - 5, label_text)
    
    def _draw_events(self, painter: QPainter, scale_x: float, scale_y: float,
                    widget_width: int, widget_height: int):
        """Отрисовать события"""
        for event in self._events:
            event_type = event.get('event_type', '')
            
            # Получить bbox и zone_coords
            box, zone_coords = EventMetadataExtractor.get_bbox_and_zone(event, False)
            
            # Отрисовать bbox
            if box:
                norm_box = EventMetadataExtractor.normalize_bbox_for_display(
                    box, self._video_width, self._video_height
                )
                
                if norm_box:
                    x1, y1, x2, y2 = norm_box
                    x = int(x1 * widget_width)
                    y = int(y1 * widget_height)
                    w = int((x2 - x1) * widget_width)
                    h = int((y2 - y1) * widget_height)
                    
                    # Цвет зависит от типа события
                    if 'zone' in event_type:
                        color = QColor(255, 0, 0)  # Красный для зон
                    elif 'attribute' in event_type:
                        color = QColor(255, 255, 0)  # Желтый для атрибутов
                    else:
                        color = QColor(0, 0, 255)  # Синий для остальных
                    
                    painter.setPen(QPen(color, 2))
                    painter.drawRect(x, y, w, h)
            
            # Отрисовать зону
            if zone_coords:
                norm_zone = EventMetadataExtractor.normalize_zone_coords(
                    zone_coords, self._video_width, self._video_height
                )
                
                if norm_zone:
                    polygon = QPolygonF()
                    for px, py in norm_zone:
                        x = int(px * widget_width)
                        y = int(py * widget_height)
                        polygon.append(QPointF(x, y))
                    
                    if polygon.count() > 0:
                        painter.setPen(QPen(QColor(255, 0, 0), 2))
                        painter.setBrush(QBrush(QColor(255, 0, 0, 64)))
                        painter.drawPolygon(polygon)
