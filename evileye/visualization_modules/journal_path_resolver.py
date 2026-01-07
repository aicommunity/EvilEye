"""
Утилиты для разрешения путей к изображениям, видео и нормализации координат
"""

import os
import re
import datetime
from typing import Optional, Tuple, List
from pathlib import Path


class JournalPathResolver:
    """Утилитный класс для разрешения путей к ресурсам журналов"""
    
    @staticmethod
    def resolve_image_path(img_path: str, base_dir: str, event_data: Optional[dict] = None, 
                          journal_type: str = 'objects', cache: Optional[dict] = None) -> Optional[str]:
        """Разрешить путь к изображению в полный абсолютный путь
        
        Args:
            img_path: Относительный путь к изображению
            base_dir: Базовый каталог данных
            event_data: Данные события (для извлечения date_folder)
            journal_type: Тип журнала ('objects' или 'events')
            cache: Опциональный кэш для результатов
            
        Returns:
            Абсолютный путь к изображению или None
        """
        if not img_path:
            return None
        
        # Создать ключ кэша
        cache_key = img_path
        if event_data:
            date_folder = event_data.get('date_folder', '')
            if date_folder:
                cache_key = f"{img_path}:{date_folder}"
        
        # Проверить кэш
        if cache is not None:
            if cache_key in cache:
                cached_path = cache[cache_key]
                if cached_path and os.path.exists(cached_path):
                    return cached_path
                del cache[cache_key]
        
        # Уже абсолютный путь
        if os.path.isabs(img_path):
            resolved = img_path if os.path.exists(img_path) else None
            if cache is not None:
                cache[cache_key] = resolved
            return resolved
        
        resolved = None
        
        # Для объектов: конвертировать frame пути в preview пути
        if journal_type == 'objects' and ('detected_frames' in img_path or 'lost_frames' in img_path):
            resolved = JournalPathResolver._resolve_object_preview_path(
                img_path, base_dir, event_data
            )
        
        # Если не разрешено, попробовать стандартные пути
        if not resolved and base_dir:
            # Прямой путь
            full_path = os.path.join(base_dir, img_path)
            if os.path.exists(full_path):
                resolved = full_path
            else:
                # Попробовать с date_folder
                if event_data:
                    date_folder = event_data.get('date_folder', '')
                    if date_folder:
                        if journal_type == 'objects':
                            candidates = [
                                os.path.join(base_dir, 'Detections', date_folder, 'Images', 'FoundPreviews', os.path.basename(img_path)),
                                os.path.join(base_dir, 'Detections', date_folder, 'Images', 'LostPreviews', os.path.basename(img_path)),
                                os.path.join(base_dir, 'images', date_folder, 'found_previews', os.path.basename(img_path)),
                                os.path.join(base_dir, 'images', date_folder, 'lost_previews', os.path.basename(img_path)),
                            ]
                        else:  # events
                            candidates = [
                                os.path.join(base_dir, 'Events', date_folder, 'Images', 'FoundPreviews', os.path.basename(img_path)),
                                os.path.join(base_dir, 'Events', date_folder, 'Images', 'LostPreviews', os.path.basename(img_path)),
                                os.path.join(base_dir, 'images', date_folder, img_path),
                            ]
                        
                        for cand in candidates:
                            if cand and os.path.exists(cand):
                                resolved = cand
                                break
                
                # Legacy пути
                if not resolved and (img_path.startswith('images' + os.sep) or img_path.startswith('images/')):
                    full_path = os.path.join(base_dir, img_path)
                    if os.path.exists(full_path):
                        resolved = full_path
        
        # Сохранить в кэш
        if cache is not None:
            cache[cache_key] = resolved
        
        return resolved
    
    @staticmethod
    def _resolve_object_preview_path(img_path: str, base_dir: str, event_data: Optional[dict]) -> Optional[str]:
        """Разрешить путь к preview изображению для объектов (конвертация из frame)"""
        filename = os.path.basename(img_path)
        
        # Конвертировать _frame.jpeg в _preview.jpeg
        if filename.endswith('_frame.jpeg'):
            preview_filename = filename.replace('_frame.jpeg', '_preview.jpeg')
        elif filename.endswith('_frame.jpg'):
            preview_filename = filename.replace('_frame.jpg', '_preview.jpg')
        else:
            name, ext = os.path.splitext(filename)
            preview_filename = f"{name}_preview{ext}"
        
        # Определить тип (found/lost) и соответствующую папку
        if 'detected_frames' in img_path:
            preview_dir = 'FoundPreviews'
        else:  # lost_frames
            preview_dir = 'LostPreviews'
        
        # Получить date_folder
        date_folder = ''
        if event_data:
            date_folder = event_data.get('date_folder', '')
        
        # Построить путь к preview
        if date_folder and base_dir:
            preview_path = os.path.join(
                base_dir, 'Detections', date_folder, 'Images', preview_dir, preview_filename
            )
            if os.path.exists(preview_path):
                return preview_path
        
        # Fallback: попробовать без date_folder (извлечь из имени файла)
        if base_dir:
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if date_match:
                extracted_date = date_match.group(1)
                preview_path = os.path.join(
                    base_dir, 'Detections', extracted_date, 'Images', preview_dir, preview_filename
                )
                if os.path.exists(preview_path):
                    return preview_path
            
            # Попробовать недавние даты
            today = datetime.datetime.now().date()
            yesterday = today - datetime.timedelta(days=1)
            for check_date in [today.strftime('%Y-%m-%d'), yesterday.strftime('%Y-%m-%d')]:
                preview_path = os.path.join(
                    base_dir, 'Detections', check_date, 'Images', preview_dir, preview_filename
                )
                if os.path.exists(preview_path):
                    return preview_path
        
        return None
    
    @staticmethod
    def resolve_frame_path(preview_path: str, journal_type: str = 'objects') -> Optional[str]:
        """Разрешить путь к frame изображению из preview пути
        
        Args:
            preview_path: Путь к preview изображению
            journal_type: Тип журнала ('objects' или 'events')
            
        Returns:
            Путь к frame изображению или None
        """
        if not preview_path or 'preview' not in preview_path.lower():
            return None
        
        # Заменить preview на frame
        frame_path = preview_path.replace('previews', 'frames').replace('_preview.', '_frame.')
        frame_path = frame_path.replace('FoundPreviews', 'FoundFrames')
        frame_path = frame_path.replace('LostPreviews', 'LostFrames')
        
        if os.path.exists(frame_path):
            return frame_path
        
        return None
    
    @staticmethod
    def normalize_bbox(box, img_w: int = 0, img_h: int = 0, img_path: str = '') -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Нормализовать координаты bounding box в диапазон [0,1]
        
        Args:
            box: Bounding box (dict, list или tuple)
            img_w: Ширина изображения (если известна)
            img_h: Высота изображения (если известна)
            img_path: Путь к изображению (для загрузки размеров, если img_w/img_h не указаны)
            
        Returns:
            Кортеж (x1, y1, x2, y2) в диапазоне [0,1] или (None, None, None, None)
        """
        if not box:
            return None, None, None, None
        
        try:
            # Загрузить размеры изображения, если не указаны
            if (img_w <= 0 or img_h <= 0) and img_path:
                try:
                    from PyQt6.QtGui import QPixmap
                except ImportError:
                    from PyQt5.QtGui import QPixmap
                
                pixmap = QPixmap(img_path)
                if not pixmap.isNull() and pixmap.width() > 0 and pixmap.height() > 0:
                    img_w = pixmap.width()
                    img_h = pixmap.height()
            
            # Обработать разные форматы box
            if isinstance(box, dict):
                x = float(box.get('x', 0))
                y = float(box.get('y', 0))
                w = float(box.get('width', 0))
                h = float(box.get('height', 0))
                
                # Проверить, нормализованы ли координаты
                if max(x, y, w, h) <= 1.0:
                    return x, y, x + w, y + h
                else:
                    # Нормализовать используя размеры изображения
                    if img_w > 0 and img_h > 0:
                        return x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = [float(x) for x in box]
                
                # Проверить формат: [x1, y1, x2, y2] или [x, y, w, h]
                if max(a, b, c, d) <= 1.0:
                    # Уже нормализовано [x1, y1, x2, y2]
                    return a, b, c, d
                else:
                    # Предполагаем [x, y, w, h] в пикселях
                    if img_w > 0 and img_h > 0:
                        return a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h
                    else:
                        # Если нет размеров, попробовать интерпретировать как [x1, y1, x2, y2]
                        return a, b, c, d
        except Exception:
            pass
        
        return None, None, None, None
