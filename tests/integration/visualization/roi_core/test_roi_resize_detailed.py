#!/usr/bin/env python3
"""
Детальные тесты для проверки проблемы с обновлением линий ROI при изменении размера
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIResizeDetailed(unittest.TestCase):
    """Детальные тесты для проверки проблемы с обновлением линий ROI"""
    
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
        
        # Настраиваем оригинальные размеры
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

    def test_real_roi_resize_with_actual_qgraphicsrectitem(self):
        """Тест изменения размера ROI с реальными QGraphicsRectItem"""
        print("\n=== ТЕСТ ИЗМЕНЕНИЯ РАЗМЕРА ROI С РЕАЛЬНЫМИ ОБЪЕКТАМИ ===")
        
        # Создаем реальный QGraphicsRectItem вместо mock
        roi_item = QGraphicsRectItem(QRectF(100, 100, 200, 150))
        roi_item.setPen(QPen(Qt.GlobalColor.red, 2))
        
        # Добавляем в scene
        self.roi_view.scene.addItem(roi_item)
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        print(f"1. Создан реальный ROI: {roi_item.rect()}")
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        print(f"2. ROI выбран, создано {len(self.roi_view.resize_handles)} маркеров")
        
        # Проверяем, что маркеры созданы
        self.assertEqual(len(self.roi_view.resize_handles), 8)
        
        # Имитируем изменение размера через setRect
        original_rect = roi_item.rect()
        new_rect = QRectF(100, 100, 250, 200)  # Увеличиваем размер
        
        print(f"3. Изменяем размер ROI:")
        print(f"   Оригинал: {original_rect}")
        print(f"   Новый: {new_rect}")
        
        # Вызываем setRect напрямую
        roi_item.setRect(new_rect)
        
        # Проверяем, что размер изменился
        updated_rect = roi_item.rect()
        print(f"   После setRect: {updated_rect}")
        
        if updated_rect.width() > original_rect.width() and updated_rect.height() > original_rect.height():
            print(f"   ✅ setRect работает корректно")
        else:
            print(f"   ❌ ПРОБЛЕМА: setRect не работает!")
        
        # Теперь тестируем _update_roi_size
        print(f"\n4. Тестируем _update_roi_size:")
        
        # Создаем mock маркер
        mock_handle = Mock()
        mock_handle.handle_index = 4  # Нижний правый маркер
        
        # Устанавливаем маркер
        self.roi_view.resize_handle = mock_handle
        
        # Новые координаты для нижнего правого маркера
        new_scene_pos = QPointF(350, 250)
        
        print(f"   Вызываем _update_roi_size с позицией: {new_scene_pos}")
        
        # Вызываем _update_roi_size
        self.roi_view._update_roi_size(new_scene_pos, mock_handle)
        
        # Проверяем результат
        final_rect = roi_item.rect()
        print(f"   После _update_roi_size: {final_rect}")
        
        if final_rect.width() > updated_rect.width() and final_rect.height() > updated_rect.height():
            print(f"   ✅ _update_roi_size работает корректно")
        else:
            print(f"   ❌ ПРОБЛЕМА: _update_roi_size не работает!")
    
    def test_roi_resize_with_mock_but_track_calls(self):
        """Тест изменения размера ROI с mock, но отслеживанием вызовов"""
        print("\n=== ТЕСТ ИЗМЕНЕНИЯ РАЗМЕРА ROI С ОТСЛЕЖИВАНИЕМ ВЫЗОВОВ ===")
        
        # Создаем mock ROI с отслеживанием вызовов
        roi_item = Mock(spec=QGraphicsRectItem)
        original_rect = QRectF(100, 100, 200, 150)
        roi_item.rect.return_value = original_rect
        roi_item.setRect = Mock()
        roi_item.zValue.return_value = 1.0
        
        # Добавляем в списки
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        print(f"1. Создан mock ROI: {original_rect}")
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        print(f"2. ROI выбран, создано {len(self.roi_view.resize_handles)} маркеров")
        
        # Создаем mock маркер
        mock_handle = Mock()
        mock_handle.handle_index = 4  # Нижний правый маркер
        
        # Устанавливаем маркер
        self.roi_view.resize_handle = mock_handle
        
        # Новые координаты
        new_scene_pos = QPointF(350, 250)
        
        print(f"3. Вызываем _update_roi_size с позицией: {new_scene_pos}")
        
        # Вызываем _update_roi_size
        self.roi_view._update_roi_size(new_scene_pos, mock_handle)
        
        # Проверяем, что setRect был вызван
        roi_item.setRect.assert_called()
        print(f"   ✅ setRect был вызван")
        
        # Получаем аргументы вызова setRect
        setRect_call_args = roi_item.setRect.call_args[0][0]
        print(f"   Аргументы setRect: {setRect_call_args}")
        
        # Проверяем, что новый прямоугольник больше оригинального
        if setRect_call_args.width() > original_rect.width() and setRect_call_args.height() > original_rect.height():
            print(f"   ✅ setRect вызван с правильными координатами")
        else:
            print(f"   ❌ ПРОБЛЕМА: setRect вызван с неправильными координатами!")
    
    def test_roi_resize_handles_position_calculation(self):
        """Тест расчета позиций маркеров изменения размера"""
        print("\n=== ТЕСТ РАСЧЕТА ПОЗИЦИЙ МАРКЕРОВ ===")
        
        # Создаем реальный ROI
        roi_item = QGraphicsRectItem(QRectF(100, 100, 200, 150))
        roi_item.setPen(QPen(Qt.GlobalColor.red, 2))
        
        # Добавляем в scene
        self.roi_view.scene.addItem(roi_item)
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        print(f"1. ROI: {roi_item.rect()}")
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        print(f"2. Создано {len(self.roi_view.resize_handles)} маркеров:")
        
        # Проверяем позиции маркеров
        expected_positions = [
            (100, 100),    # 0: Верхний левый
            (200, 100),    # 1: Верхний центр
            (300, 100),    # 2: Верхний правый
            (300, 175),    # 3: Правый центр
            (300, 250),    # 4: Нижний правый
            (200, 250),    # 5: Нижний центр
            (100, 250),    # 6: Нижний левый
            (100, 175)     # 7: Левый центр
        ]
        
        for i, handle in enumerate(self.roi_view.resize_handles):
            handle_rect = handle.rect()
            expected_x, expected_y = expected_positions[i]
            actual_x = handle_rect.x()
            actual_y = handle_rect.y()
            
            print(f"   Маркер {i}: ожидается ({expected_x}, {expected_y}), фактически ({actual_x}, {actual_y})")
            
            if abs(actual_x - expected_x) < 1 and abs(actual_y - expected_y) < 1:
                print(f"   ✅ Маркер {i} в правильной позиции")
            else:
                print(f"   ❌ Маркер {i} в неправильной позиции!")
    
    def test_roi_resize_with_different_handle_indices(self):
        """Тест изменения размера ROI с разными индексами маркеров"""
        print("\n=== ТЕСТ ИЗМЕНЕНИЯ РАЗМЕРА С РАЗНЫМИ МАРКЕРАМИ ===")
        
        # Создаем реальный ROI
        roi_item = QGraphicsRectItem(QRectF(100, 100, 200, 150))
        roi_item.setPen(QPen(Qt.GlobalColor.red, 2))
        
        # Добавляем в scene
        self.roi_view.scene.addItem(roi_item)
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        print(f"1. ROI: {roi_item.rect()}")
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        # Тестируем разные маркеры
        test_cases = [
            (0, QPointF(50, 50), "Верхний левый"),      # Уменьшаем и сдвигаем влево-вверх
            (2, QPointF(350, 50), "Верхний правый"),    # Увеличиваем ширину, уменьшаем высоту
            (4, QPointF(350, 300), "Нижний правый"),    # Увеличиваем размер
            (6, QPointF(50, 300), "Нижний левый"),      # Уменьшаем и сдвигаем влево-вниз
        ]
        
        for handle_index, new_pos, description in test_cases:
            print(f"\n2. Тестируем маркер {handle_index} ({description}):")
            print(f"   Новая позиция: {new_pos}")
            
            # Создаем mock маркер
            mock_handle = Mock()
            mock_handle.handle_index = handle_index
            
            # Устанавливаем маркер
            self.roi_view.resize_handle = mock_handle
            
            # Запоминаем оригинальный размер
            original_rect = roi_item.rect()
            print(f"   Оригинал: {original_rect}")
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_pos, mock_handle)
            
            # Проверяем результат
            updated_rect = roi_item.rect()
            print(f"   После обновления: {updated_rect}")
            
            # Проверяем, что что-то изменилось
            if updated_rect != original_rect:
                print(f"   ✅ ROI изменился")
            else:
                print(f"   ❌ ПРОБЛЕМА: ROI не изменился!")


if __name__ == '__main__':
    unittest.main()
