"""
Базовый класс для унифицированных журналов объектов и событий
"""

import os
import sys
from pathlib import Path
from typing import Optional, Dict

try:
    from PyQt6.QtWidgets import QWidget
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QWidget
    pyqt_version = 5

# Add parent directory to path for imports
sys.path.append(str(Path(__file__).parent.parent.parent))

from .journal_data_source import EventJournalDataSource
from .journal_path_resolver import JournalPathResolver
import logging


class UnifiedJournalBase(QWidget):
    """Базовый класс для унифицированных журналов с общими методами"""
    
    def __init__(self, data_source: EventJournalDataSource, base_dir: str = None,
                 parent=None, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        """Инициализация базового журнала
        
        Args:
            data_source: Источник данных журнала
            base_dir: Базовый каталог данных
            parent: Родительский виджет
            logger_name: Имя логгера
            parent_logger: Родительский логгер
        """
        super().__init__(parent)
        
        self.data_source = data_source
        
        # Получить base_dir из data_source если не указан
        if base_dir:
            self.base_dir = base_dir
        else:
            image_dir = getattr(data_source, 'image_dir', None)
            if image_dir:
                self.base_dir = image_dir
            else:
                base_dir_attr = getattr(data_source, 'base_dir', None)
                self.base_dir = base_dir_attr if base_dir_attr else ''
        
        # Кэш для разрешенных путей к изображениям
        self._image_path_cache = {}
        
        # Инициализировать логгер
        if parent_logger:
            self.logger = parent_logger
        elif logger_name:
            self.logger = logging.getLogger(logger_name)
        else:
            self.logger = logging.getLogger(self.__class__.__name__)
    
    def _resolve_image_path(self, img_path: str, event_data: Optional[dict] = None) -> Optional[str]:
        """Разрешить путь к изображению в полный абсолютный путь
        
        Args:
            img_path: Относительный путь к изображению
            event_data: Данные события (для извлечения date_folder)
            
        Returns:
            Абсолютный путь к изображению или None
        """
        journal_type = 'objects' if 'objects' in self.__class__.__name__.lower() else 'events'
        return JournalPathResolver.resolve_image_path(
            img_path, self.base_dir, event_data, journal_type, self._image_path_cache
        )
    
    def _resolve_frame_path(self, preview_path: str, event_data: Optional[dict] = None) -> Optional[str]:
        """Разрешить путь к frame изображению из preview пути
        
        Args:
            preview_path: Путь к preview изображению
            event_data: Данные события (не используется, но оставлен для совместимости)
            
        Returns:
            Путь к frame изображению или None
        """
        journal_type = 'objects' if 'objects' in self.__class__.__name__.lower() else 'events'
        return JournalPathResolver.resolve_frame_path(preview_path, journal_type)
    
    def _normalize_bbox(self, box, img_path: str = '') -> Optional[list]:
        """Нормализовать координаты bounding box в формат [x1, y1, x2, y2] в диапазоне [0,1]
        
        Args:
            box: Bounding box (dict, list или tuple)
            img_path: Путь к изображению для загрузки размеров
            
        Returns:
            Нормализованный список [x1, y1, x2, y2] или None
        """
        x1, y1, x2, y2 = JournalPathResolver.normalize_bbox(box, img_path=img_path)
        if x1 is not None and y1 is not None and x2 is not None and y2 is not None:
            return [x1, y1, x2, y2]
        return None
