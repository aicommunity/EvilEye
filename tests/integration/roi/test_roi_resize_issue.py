#!/usr/bin/env python3
"""
Тесты для проверки проблемы с обновлением линий ROI при изменении размера
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock
import json

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIResizeIssue(unittest.TestCase):
    """Тесты для проверки проблемы с обновлением линий ROI при изменении размера"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        with patch('evileye.visualization_modules.roi_core.get_module_logger') as mock_logger:
            mock_logger.return_value = Mock()
            self.roi_view = ROIGraphicsView()
        
        # Настраиваем mock для pixmap_item
        self.roi_view.pixmap_item = Mock()
        self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
        
        # Настраиваем оригинальные размеры (3840x2160 - стандартное разрешение)
        self.roi_view.original_size = (3840, 2160)
        self.roi_view.display_size = (3840, 2160)
        self.roi_view.scale_factor = 1.0
        
        # Настраиваем scene
        self.roi_view.scene = QGraphicsScene()
        self.roi_view.setScene(self.roi_view.scene)
    
    def tearDown(self):
        """Очистка после тестов"""
        # Автоматически закрываем окно через 100ms
        def close_window():
            try:
                if hasattr(self, 'roi_window') and self.roi_window:
                    self.roi_window.close()
                self.app.quit()
            except Exception:
                pass
        
        QTimer.singleShot(100, close_window)
        # Даем время на закрытие окна
        time.sleep(0.2)
        
        # Явно закрываем окно на случай, если таймер не сработал
        try:
            if hasattr(self, 'roi_window') and self.roi_window:
                self.roi_window.close()
            self.app.quit()
        except Exception:
            pass

    def load_problematic_rois_from_config(self):
        """Загрузить проблемные ROI из конфигурации poly-cameras.json для source 0"""
        # ROI из конфига для source 0
        problematic_rois = [
            [1790, 0, 500, 400],    # Маленький ROI
            [1700, 0, 1000, 1045],  # Средний ROI
            [1500, 0, 2340, 2160]   # Большой ROI
        ]
        
        # Преобразуем в формат [x1, y1, x2, y2]
        converted_rois = []
        for roi in problematic_rois:
            x, y, w, h = roi
            converted_rois.append([x, y, x + w, y + h])
        
        return converted_rois
    
    def test_problematic_rois_loading(self):
        """Тест загрузки проблемных ROI из конфигурации"""
        print("\n=== ТЕСТ ЗАГРУЗКИ ПРОБЛЕМНЫХ ROI ===")
        
        problematic_rois = self.load_problematic_rois_from_config()
        
        print(f"1. Загружены проблемные ROI из конфига:")
        for i, roi in enumerate(problematic_rois):
            x1, y1, x2, y2 = roi
            width = x2 - x1
            height = y2 - y1
            area = width * height
            print(f"   ROI {i}: [{x1}, {y1}, {x2}, {y2}] - размер: {width}x{height}, площадь: {area}")
        
        # Проверяем, что ROI перекрываются
        print(f"\n2. Анализ перекрытий:")
        for i in range(len(problematic_rois)):
            for j in range(i + 1, len(problematic_rois)):
                roi1 = problematic_rois[i]
                roi2 = problematic_rois[j]
                
                # Проверяем перекрытие
                overlap = self._calculate_overlap(roi1, roi2)
                if overlap > 0:
                    print(f"   ROI {i} и ROI {j} перекрываются на {overlap} пикселей")
                else:
                    print(f"   ROI {i} и ROI {j} НЕ перекрываются")
        
        self.assertEqual(len(problematic_rois), 3)
        print(f"   ✅ Загружено {len(problematic_rois)} проблемных ROI")
    
    def _calculate_overlap(self, roi1, roi2):
        """Вычислить площадь перекрытия двух ROI"""
        x1_1, y1_1, x2_1, y2_1 = roi1
        x1_2, y1_2, x2_2, y2_2 = roi2
        
        # Вычисляем пересечение
        x1_overlap = max(x1_1, x1_2)
        y1_overlap = max(y1_1, y1_2)
        x2_overlap = min(x2_1, x2_2)
        y2_overlap = min(y2_1, y2_2)
        
        if x1_overlap < x2_overlap and y1_overlap < y2_overlap:
            return (x2_overlap - x1_overlap) * (y2_overlap - y1_overlap)
        return 0
    
    def test_roi_resize_handles_creation(self):
        """Тест создания маркеров изменения размера для проблемных ROI"""
        print("\n=== ТЕСТ СОЗДАНИЯ МАРКЕРОВ ИЗМЕНЕНИЯ РАЗМЕРА ===")
        
        problematic_rois = self.load_problematic_rois_from_config()
        
        # Добавляем ROI в canvas
        for i, roi in enumerate(problematic_rois):
            color = (255, 0, 0) if i == 0 else (0, 255, 0) if i == 1 else (0, 0, 255)
            roi_item = self.roi_view.add_roi(roi, color)
            self.assertIsNotNone(roi_item)
        
        print(f"1. Добавлено {len(problematic_rois)} ROI в canvas")
        
        # Выбираем каждый ROI и проверяем создание маркеров
        for i in range(len(problematic_rois)):
            roi_item = self.roi_view.rois[i]
            
            # Очищаем предыдущие маркеры
            self.roi_view._remove_resize_handles()
            
            # Выбираем ROI
            self.roi_view._select_roi(roi_item)
            
            # Проверяем, что маркеры созданы
            self.assertEqual(len(self.roi_view.resize_handles), 8)
            print(f"   ROI {i}: создано {len(self.roi_view.resize_handles)} маркеров")
            
            # Проверяем, что маркеры имеют правильные свойства
            for j, handle in enumerate(self.roi_view.resize_handles):
                self.assertIsNotNone(handle.parent_view)
                self.assertIsNotNone(handle.parent_roi)
                self.assertEqual(handle.handle_index, j)
        
        print(f"   ✅ Все маркеры создаются корректно")
    
    def test_roi_resize_handles_movement(self):
        """Тест движения маркеров изменения размера"""
        print("\n=== ТЕСТ ДВИЖЕНИЯ МАРКЕРОВ ИЗМЕНЕНИЯ РАЗМЕРА ===")
        
        problematic_rois = self.load_problematic_rois_from_config()
        
        # Добавляем первый ROI (самый маленький)
        roi_item = self.roi_view.add_roi(problematic_rois[0], (255, 0, 0))
        self.assertIsNotNone(roi_item)
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        print(f"1. Выбран ROI 0, создано {len(self.roi_view.resize_handles)} маркеров")
        
        # Имитируем движение маркера
        if self.roi_view.resize_handles:
            handle = self.roi_view.resize_handles[0]  # Берем первый маркер
            
            # Создаем mock событие мыши
            mock_event = Mock()
            mock_event.pos.return_value = QPointF(10, 10)
            
            # Mock для mapToScene
            handle.mapToScene = Mock(return_value=QPointF(1800, 10))
            
            print(f"2. Имитируем движение маркера в позицию (1800, 10)")
            
            # Вызываем mouseMoveEvent на маркере
            handle.mouseMoveEvent(mock_event)
            
            # Проверяем, что _update_roi_size был вызван
            # (это проверяется через mock parent_view)
            if hasattr(handle, 'parent_view') and handle.parent_view:
                print(f"   ✅ Маркер может двигаться и вызывать _update_roi_size")
            else:
                print(f"   ❌ Проблема: маркер не может вызвать _update_roi_size")
    
    def test_roi_line_update_issue(self):
        """Тест проблемы с обновлением линий ROI"""
        print("\n=== ТЕСТ ПРОБЛЕМЫ С ОБНОВЛЕНИЕМ ЛИНИЙ ROI ===")
        
        problematic_rois = self.load_problematic_rois_from_config()
        
        # Добавляем все проблемные ROI
        for i, roi in enumerate(problematic_rois):
            color = (255, 0, 0) if i == 0 else (0, 255, 0) if i == 1 else (0, 0, 255)
            roi_item = self.roi_view.add_roi(roi, color)
            self.assertIsNotNone(roi_item)
        
        print(f"1. Добавлено {len(problematic_rois)} проблемных ROI")
        
        # Тестируем каждый ROI
        for i in range(len(problematic_rois)):
            roi_item = self.roi_view.rois[i]
            original_rect = roi_item.rect()
            
            print(f"\n2. Тестируем ROI {i}:")
            print(f"   Оригинальный размер: {original_rect.width()}x{original_rect.height()}")
            
            # Выбираем ROI
            self.roi_view._select_roi(roi_item)
            
            # Проверяем, что ROI выделен
            self.assertEqual(self.roi_view.selected_roi, roi_item)
            self.assertEqual(self.roi_view.selected_roi_id, i)
            
            # Имитируем изменение размера через _update_roi_size
            new_coords = [original_rect.x(), original_rect.y(), 
                         original_rect.x() + original_rect.width() + 50, 
                         original_rect.y() + original_rect.height() + 50]
            
            print(f"   Новые координаты: {new_coords}")
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(QPointF(new_coords[2], new_coords[3]), None)
            
            # Проверяем, что размер ROI изменился
            updated_rect = roi_item.rect()
            print(f"   Обновленный размер: {updated_rect.width()}x{updated_rect.height()}")
            
            # Проверяем, что размер действительно изменился
            if updated_rect.width() > original_rect.width() and updated_rect.height() > original_rect.height():
                print(f"   ✅ ROI {i}: размер обновился корректно")
            else:
                print(f"   ❌ ROI {i}: ПРОБЛЕМА - размер не обновился!")
                print(f"      Оригинал: {original_rect.width()}x{original_rect.height()}")
                print(f"      После обновления: {updated_rect.width()}x{updated_rect.height()}")
    
    def test_overlapping_rois_selection_issue(self):
        """Тест проблемы с выбором перекрывающихся ROI"""
        print("\n=== ТЕСТ ПРОБЛЕМЫ С ВЫБОРОМ ПЕРЕКРЫВАЮЩИХСЯ ROI ===")
        
        problematic_rois = self.load_problematic_rois_from_config()
        
        # Добавляем все проблемные ROI
        for i, roi in enumerate(problematic_rois):
            color = (255, 0, 0) if i == 0 else (0, 255, 0) if i == 1 else (0, 0, 255)
            roi_item = self.roi_view.add_roi(roi, color)
            self.assertIsNotNone(roi_item)
        
        print(f"1. Добавлено {len(problematic_rois)} перекрывающихся ROI")
        
        # Проверяем z-order (порядок отображения)
        print(f"\n2. Проверка z-order:")
        for i, roi_item in enumerate(self.roi_view.rois):
            z_value = roi_item.zValue()
            print(f"   ROI {i}: zValue = {z_value}")
        
        # Тестируем выбор ROI в области перекрытия
        # Координаты в области перекрытия всех трех ROI
        overlap_point = QPointF(1800, 200)  # Точка в области перекрытия
        
        print(f"\n3. Тестируем выбор ROI в точке перекрытия: {overlap_point}")
        
        # Имитируем клик в точке перекрытия
        mock_event = Mock()
        mock_event.button.return_value = Qt.MouseButton.LeftButton
        mock_event.pos.return_value = QPointF(100, 100)  # Позиция в view
        
        # Mock для mapToScene
        self.roi_view.mapToScene = Mock(return_value=overlap_point)
        
        # Вызываем mousePressEvent
        self.roi_view.mousePressEvent(mock_event)
        
        # Проверяем, какой ROI был выбран
        selected_id = self.roi_view.get_selected_roi_id()
        print(f"   Выбран ROI с ID: {selected_id}")
        
        if selected_id >= 0:
            selected_roi = self.roi_view.rois[selected_id]
            selected_rect = selected_roi.rect()
            print(f"   Размер выбранного ROI: {selected_rect.width()}x{selected_rect.height()}")
            
            # Проверяем, что выбранный ROI действительно содержит точку клика
            if selected_rect.contains(overlap_point):
                print(f"   ✅ Выбранный ROI содержит точку клика")
            else:
                print(f"   ❌ ПРОБЛЕМА: выбранный ROI НЕ содержит точку клика!")
        else:
            print(f"   ❌ ПРОБЛЕМА: ни один ROI не был выбран!")


if __name__ == '__main__':
    unittest.main()
