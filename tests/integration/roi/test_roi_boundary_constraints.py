#!/usr/bin/env python3
"""
Тест для проверки ограничений границ ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIBoundaryConstraints(unittest.TestCase):
    """Тест для проверки ограничений границ ROI"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        with patch('evileye.visualization_modules.dialogs.roi_editor_dialog.get_module_logger') as mock_logger:
            mock_logger.return_value = Mock()
            self.roi_view = ROIGraphicsView()
        
        # Настраиваем mock для pixmap_item
        self.roi_view.pixmap_item = Mock()
        self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
        
        # Настраиваем размеры экрана
        self.screen_width = 3840
        self.screen_height = 2160
        self.roi_view.original_size = (self.screen_width, self.screen_height)
        self.roi_view.display_size = (self.screen_width, self.screen_height)
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

    def test_constrain_roi_to_screen_bounds(self):
        """Тест метода _constrain_roi_to_screen_bounds"""
        print("\n=== ТЕСТ МЕТОДА _constrain_roi_to_screen_bounds ===")
        
        test_cases = [
            # (input_rect, expected_result, description)
            (QRectF(100, 100, 200, 150), QRectF(100, 100, 200, 150), "Нормальный ROI в пределах экрана"),
            (QRectF(-50, 100, 200, 150), QRectF(0, 100, 200, 150), "ROI выходит за левую границу"),
            (QRectF(100, -50, 200, 150), QRectF(100, 0, 200, 150), "ROI выходит за верхнюю границу"),
            (QRectF(3700, 100, 200, 150), QRectF(3640, 100, 200, 150), "ROI выходит за правую границу"),
            (QRectF(100, 2100, 200, 150), QRectF(100, 2010, 200, 150), "ROI выходит за нижнюю границу"),
            (QRectF(-50, -50, 200, 150), QRectF(0, 0, 200, 150), "ROI выходит за левую и верхнюю границы"),
            (QRectF(3700, 2100, 200, 150), QRectF(3640, 2010, 200, 150), "ROI выходит за правую и нижнюю границы"),
            (QRectF(100, 100, 4000, 2500), QRectF(100, 100, 3740, 2060), "ROI слишком большой"),
        ]
        
        for i, (input_rect, expected_result, description) in enumerate(test_cases):
            print(f"\n{i+1}. {description}")
            print(f"   Входной ROI: {input_rect}")
            
            # Вызываем метод
            result = self.roi_view._constrain_roi_to_screen_bounds(input_rect)
            
            print(f"   Результат: {result}")
            print(f"   Ожидаемый: {expected_result}")
            
            # Проверяем результат
            if result == expected_result:
                print(f"   ✅ Результат корректный")
            else:
                print(f"   ❌ ПРОБЛЕМА: результат не соответствует ожидаемому!")
            
            # Проверяем, что ROI в пределах экрана
            within_bounds = (
                result.left() >= 0 and
                result.top() >= 0 and
                result.right() <= self.screen_width and
                result.bottom() <= self.screen_height
            )
            
            if within_bounds:
                print(f"   ✅ ROI в пределах экрана")
            else:
                print(f"   ❌ ПРОБЛЕМА: ROI все еще выходит за границы экрана!")
    
    def test_roi_resize_with_boundary_constraints(self):
        """Тест изменения размера ROI с ограничениями границ"""
        print("\n=== ТЕСТ ИЗМЕНЕНИЯ РАЗМЕРА ROI С ОГРАНИЧЕНИЯМИ ГРАНИЦ ===")
        
        # Создаем ROI
        roi_item = self.roi_view.add_roi([100, 100, 300, 250], (255, 0, 0))
        self.assertIsNotNone(roi_item)
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        print(f"1. Создан ROI: {roi_item.rect()}")
        
        # Тестируем разные сценарии выхода за границы
        test_cases = [
            (QPointF(-50, 100), "Выход за левую границу"),
            (QPointF(100, -50), "Выход за верхнюю границу"),
            (QPointF(self.screen_width + 50, 100), "Выход за правую границу"),
            (QPointF(100, self.screen_height + 50), "Выход за нижнюю границу"),
            (QPointF(200, 200), "Нормальные координаты"),
        ]
        
        for new_pos, description in test_cases:
            print(f"\n2. Тестируем: {description}")
            print(f"   Новая позиция: {new_pos}")
            
            # Устанавливаем маркер
            mock_handle = Mock()
            mock_handle.handle_index = 4  # Нижний правый маркер
            self.roi_view.resize_handle = mock_handle
            
            # Запоминаем оригинальный размер
            original_rect = roi_item.rect()
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_pos, mock_handle)
            
            # Проверяем результат
            updated_rect = roi_item.rect()
            print(f"   Результат: {updated_rect}")
            
            # Проверяем границы
            within_bounds = (
                updated_rect.left() >= 0 and
                updated_rect.top() >= 0 and
                updated_rect.right() <= self.screen_width and
                updated_rect.bottom() <= self.screen_height
            )
            
            if within_bounds:
                print(f"   ✅ ROI в пределах экрана")
            else:
                print(f"   ❌ ПРОБЛЕМА: ROI вышел за границы экрана!")
                print(f"      left={updated_rect.left()}, top={updated_rect.top()}")
                print(f"      right={updated_rect.right()}, bottom={updated_rect.bottom()}")
                print(f"      screen={self.screen_width}x{self.screen_height}")
    
    def test_problematic_source0_rois_with_constraints(self):
        """Тест проблемных ROI из source 0 с ограничениями"""
        print("\n=== ТЕСТ ПРОБЛЕМНЫХ ROI ИЗ SOURCE 0 С ОГРАНИЧЕНИЯМИ ===")
        
        # Проблемные ROI из source 0
        problematic_rois = [
            [1790, 0, 500, 400],    # Маленький ROI
            [1700, 0, 1000, 1045],  # Средний ROI
            [1500, 0, 2340, 2160]   # Большой ROI
        ]
        
        print(f"1. Тестируем {len(problematic_rois)} проблемных ROI из source 0:")
        
        for i, roi in enumerate(problematic_rois):
            x, y, w, h = roi
            roi_coords = [x, y, x + w, y + h]  # Преобразуем в [x1, y1, x2, y2]
            
            print(f"\n   ROI {i}: {roi_coords}")
            
            # Добавляем ROI
            roi_item = self.roi_view.add_roi(roi_coords, (255, 0, 0))
            self.assertIsNotNone(roi_item)
            
            # Проверяем, что ROI в пределах экрана
            rect = roi_item.rect()
            within_bounds = (
                rect.left() >= 0 and
                rect.top() >= 0 and
                rect.right() <= self.screen_width and
                rect.bottom() <= self.screen_height
            )
            
            if within_bounds:
                print(f"   ✅ ROI {i} в пределах экрана")
            else:
                print(f"   ❌ ПРОБЛЕМА: ROI {i} вышел за границы экрана!")
                print(f"      rect={rect}")
                print(f"      screen={self.screen_width}x{self.screen_height}")
            
            # Тестируем изменение размера
            self.roi_view._select_roi(roi_item)
            
            # Устанавливаем маркер
            mock_handle = Mock()
            mock_handle.handle_index = 4  # Нижний правый маркер
            self.roi_view.resize_handle = mock_handle
            
            # Пытаемся увеличить ROI за границы экрана
            new_pos = QPointF(self.screen_width + 100, self.screen_height + 100)
            
            print(f"   Пытаемся изменить размер до: {new_pos}")
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_pos, mock_handle)
            
            # Проверяем результат
            updated_rect = roi_item.rect()
            within_bounds_after = (
                updated_rect.left() >= 0 and
                updated_rect.top() >= 0 and
                updated_rect.right() <= self.screen_width and
                updated_rect.bottom() <= self.screen_height
            )
            
            if within_bounds_after:
                print(f"   ✅ ROI {i} остался в пределах экрана после изменения размера")
            else:
                print(f"   ❌ ПРОБЛЕМА: ROI {i} вышел за границы экрана после изменения размера!")
                print(f"      updated_rect={updated_rect}")
    
    def test_boundary_constraints_with_different_screen_sizes(self):
        """Тест ограничений границ с разными размерами экрана"""
        print("\n=== ТЕСТ ОГРАНИЧЕНИЙ ГРАНИЦ С РАЗНЫМИ РАЗМЕРАМИ ЭКРАНА ===")
        
        screen_sizes = [
            (1920, 1080, "Full HD"),
            (2560, 1440, "2K"),
            (3840, 2160, "4K"),
            (5120, 2880, "5K"),
        ]
        
        for width, height, name in screen_sizes:
            print(f"\n1. Тестируем {name} ({width}x{height}):")
            
            # Устанавливаем размер экрана
            self.roi_view.original_size = (width, height)
            
            # Создаем ROI, который выходит за границы
            roi_coords = [width - 100, height - 100, width + 200, height + 200]
            roi_item = self.roi_view.add_roi(roi_coords, (255, 0, 0))
            
            if roi_item:
                rect = roi_item.rect()
                within_bounds = (
                    rect.left() >= 0 and
                    rect.top() >= 0 and
                    rect.right() <= width and
                    rect.bottom() <= height
                )
                
                if within_bounds:
                    print(f"   ✅ ROI ограничен границами {width}x{height}")
                else:
                    print(f"   ❌ ПРОБЛЕМА: ROI не ограничен границами {width}x{height}")
                    print(f"      rect={rect}")


if __name__ == '__main__':
    unittest.main()
