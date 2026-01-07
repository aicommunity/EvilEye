"""
Извлечение метаданных событий для отображения в журналах
"""

from typing import Optional, Tuple, List, Dict


class EventMetadataExtractor:
    """Класс для извлечения метаданных событий из различных источников"""
    
    @staticmethod
    def get_bbox_and_zone(event_data: dict, is_lost: bool = False) -> Tuple[Optional[List[float]], Optional[List]]:
        """Извлечь bounding box и zone coordinates из данных события
        
        Учитывает различные форматы данных:
        - Для событий из БД: могут быть поля box_entered/box_left или bounding_box/lost_bounding_box
        - Для событий из JSON: могут быть различные поля в зависимости от типа события
        
        Args:
            event_data: Словарь с данными события
            is_lost: True если нужно извлечь данные для lost события
            
        Returns:
            Кортеж (bbox, zone_coords), где:
            - bbox: список [x1, y1, x2, y2] или [x, y, w, h] в зависимости от формата
            - zone_coords: список координат зоны [(x1, y1), (x2, y2), ...] или None
        """
        if not event_data:
            return None, None
        
        event_type = event_data.get('event_type', '')
        box = None
        zone_coords = None
        
        # Обработать разные типы событий
        if event_type in ('zone_entered', 'zone_left'):
            # ZoneEvent: использовать box_entered/box_left или bounding_box/lost_bounding_box
            if is_lost:
                # Попробовать разные варианты полей
                box = (event_data.get('box_left') or 
                      event_data.get('lost_bounding_box') or 
                      event_data.get('bounding_box'))
            else:
                box = (event_data.get('box_entered') or 
                      event_data.get('bounding_box'))
            
            zone_coords = event_data.get('zone_coords')
            
        elif event_type in ('attr_found', 'attr_lost'):
            # AttributeEvent: использовать box_found/box_finished или bounding_box/lost_bounding_box
            if is_lost:
                box = (event_data.get('box_finished') or 
                      event_data.get('lost_bounding_box') or 
                      event_data.get('bounding_box'))
            else:
                box = (event_data.get('box_found') or 
                      event_data.get('bounding_box'))
            
        elif event_type in ('found', 'lost', 'ObjectEvent'):
            # ObjectEvent: использовать bounding_box
            box = event_data.get('bounding_box') or event_data.get('box')
            
        else:
            # Fallback: попробовать общие поля
            if is_lost:
                box = (event_data.get('lost_bounding_box') or 
                      event_data.get('bounding_box') or 
                      event_data.get('box'))
            else:
                box = event_data.get('bounding_box') or event_data.get('box')
            
            zone_coords = event_data.get('zone_coords')
        
        return box, zone_coords
    
    @staticmethod
    def normalize_bbox_for_display(box, img_w: int, img_h: int) -> Optional[List[float]]:
        """Нормализовать bounding box для отображения с учетом размеров изображения
        
        Args:
            box: Bounding box в любом формате (dict, list, tuple)
            img_w: Ширина изображения
            img_h: Высота изображения
            
        Returns:
            Нормализованный список [x1, y1, x2, y2] в диапазоне [0,1] или None
        """
        if not box or img_w <= 0 or img_h <= 0:
            return None
        
        try:
            # Обработать dict формат
            if isinstance(box, dict):
                x = float(box.get('x', 0))
                y = float(box.get('y', 0))
                w = float(box.get('width', 0))
                h = float(box.get('height', 0))
                
                # Если координаты уже нормализованы
                if max(x, y, w, h) <= 1.0:
                    return [x, y, x + w, y + h]
                else:
                    # Нормализовать
                    return [x / img_w, y / img_h, (x + w) / img_w, (y + h) / img_h]
            
            # Обработать list/tuple формат
            elif isinstance(box, (list, tuple)) and len(box) == 4:
                a, b, c, d = [float(x) for x in box]
                
                # Если уже нормализовано [x1, y1, x2, y2]
                if max(a, b, c, d) <= 1.0:
                    return [a, b, c, d]
                else:
                    # Предполагаем [x, y, w, h] в пикселях
                    return [a / img_w, b / img_h, (a + c) / img_w, (b + d) / img_h]
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def normalize_zone_coords(zone_coords, img_w: int, img_h: int) -> Optional[List[Tuple[float, float]]]:
        """Нормализовать координаты зоны для отображения
        
        Args:
            zone_coords: Координаты зоны (список кортежей или строка)
            img_w: Ширина изображения
            img_h: Высота изображения
            
        Returns:
            Нормализованный список кортежей [(x1, y1), (x2, y2), ...] или None
        """
        if not zone_coords or img_w <= 0 or img_h <= 0:
            return None
        
        try:
            # Если строка, распарсить
            if isinstance(zone_coords, str):
                zone_coords = EventMetadataExtractor._parse_zone_coords_string(zone_coords)
            
            # Если список кортежей
            if isinstance(zone_coords, (list, tuple)):
                normalized = []
                for coord in zone_coords:
                    if isinstance(coord, (list, tuple)) and len(coord) == 2:
                        px, py = float(coord[0]), float(coord[1])
                        
                        # Если координаты уже нормализованы
                        if px <= 1.0 and py <= 1.0:
                            normalized.append((px, py))
                        else:
                            # Нормализовать
                            normalized.append((px / img_w, py / img_h))
                
                return normalized if normalized else None
        except Exception:
            pass
        
        return None
    
    @staticmethod
    def _parse_zone_coords_string(zone_str: str) -> Optional[List[Tuple[float, float]]]:
        """Распарсить строку координат зоны из БД формата"""
        try:
            s = zone_str.strip().strip('{}')
            points_str = [p.strip('{} ') for p in s.split('},')]
            coords = []
            for ps in points_str:
                parts = [pp.strip() for pp in ps.split(',') if pp.strip()]
                if len(parts) == 2:
                    coords.append((float(parts[0]), float(parts[1])))
            return coords if coords else None
        except Exception:
            return None
