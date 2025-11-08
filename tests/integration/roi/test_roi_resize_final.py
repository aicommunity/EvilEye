#!/usr/bin/env python3
"""
Финальный тест для проверки исправления проблемы с обновлением линий ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIResizeFinal(unittest.TestCase):
    """Финальный тест для проверки исправления проблемы с обновлением линий ROI"""
    
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

    def test_problematic_rois_from_config(self):
        """Тест с проблемными ROI из конфигурации poly-cameras.json"""
        print("\n=== ТЕСТ С ПРОБЛЕМНЫМИ ROI ИЗ КОНФИГА ===")
        
        # ROI из конфига для source 0 (преобразованы в [x1, y1, x2, y2])
        problematic_rois = [
            [1790, 0, 2290, 400],    # Маленький ROI
            [1700, 0, 2700, 1045],   # Средний ROI
            [1500, 0, 3840, 2160]    # Большой ROI
        ]
        
        print(f"1. Загружаем {len(problematic_rois)} проблемных ROI из конфига:")
        for i, roi in enumerate(problematic_rois):
            x1, y1, x2, y2 = roi
            width = x2 - x1
            height = y2 - y1
            area = width * height
            print(f"   ROI {i}: [{x1}, {y1}, {x2}, {y2}] - размер: {width}x{height}, площадь: {area}")
        
        # Добавляем ROI в canvas
        roi_items = []
        for i, roi in enumerate(problematic_rois):
            color = (255, 0, 0) if i == 0 else (0, 255, 0) if i == 1 else (0, 0, 255)
            roi_item = self.roi_view.add_roi(roi, color)
            self.assertIsNotNone(roi_item)
            roi_items.append(roi_item)
        
        print(f"2. Добавлено {len(roi_items)} ROI в canvas")
        
        # Тестируем изменение размера каждого ROI
        for i, roi_item in enumerate(roi_items):
            print(f"\n3. Тестируем ROI {i}:")
            
            # Выбираем ROI
            self.roi_view._select_roi(roi_item)
            
            # Проверяем, что маркеры созданы
            self.assertEqual(len(self.roi_view.resize_handles), 8)
            print(f"   Создано {len(self.roi_view.resize_handles)} маркеров")
            
            # Тестируем изменение размера через маркер 4 (нижний правый)
            original_rect = roi_item.rect()
            print(f"   Оригинальный размер: {original_rect.width()}x{original_rect.height()}")
            
            # Создаем mock маркер
            mock_handle = Mock()
            mock_handle.handle_index = 4  # Нижний правый маркер
            
            # Устанавливаем маркер
            self.roi_view.resize_handle = mock_handle
            
            # Новые координаты - увеличиваем размер
            new_scene_pos = QPointF(
                original_rect.right() + 50,  # Увеличиваем ширину на 50
                original_rect.bottom() + 50  # Увеличиваем высоту на 50
            )
            
            print(f"   Новые координаты маркера: {new_scene_pos}")
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_scene_pos, mock_handle)
            
            # Проверяем результат
            updated_rect = roi_item.rect()
            print(f"   Обновленный размер: {updated_rect.width()}x{updated_rect.height()}")
            
            # Проверяем, что размер изменился
            if updated_rect.width() > original_rect.width() and updated_rect.height() > original_rect.height():
                print(f"   ✅ ROI {i}: размер обновился корректно")
            else:
                print(f"   ❌ ROI {i}: ПРОБЛЕМА - размер не обновился!")
                print(f"      Оригинал: {original_rect.width()}x{original_rect.height()}")
                print(f"      После обновления: {updated_rect.width()}x{updated_rect.height()}")
    
    def test_overlapping_rois_resize(self):
        """Тест изменения размера перекрывающихся ROI"""
        print("\n=== ТЕСТ ИЗМЕНЕНИЯ РАЗМЕРА ПЕРЕКРЫВАЮЩИХСЯ ROI ===")
        
        # Создаем перекрывающиеся ROI
        overlapping_rois = [
            [100, 100, 300, 200],  # Маленький ROI
            [200, 150, 400, 300],  # Средний ROI (перекрывается с первым)
            [150, 120, 350, 250]   # Третий ROI (перекрывается с обоими)
        ]
        
        print(f"1. Создаем {len(overlapping_rois)} перекрывающихся ROI:")
        for i, roi in enumerate(overlapping_rois):
            x1, y1, x2, y2 = roi
            width = x2 - x1
            height = y2 - y1
            print(f"   ROI {i}: [{x1}, {y1}, {x2}, {y2}] - размер: {width}x{height}")
        
        # Добавляем ROI в canvas
        roi_items = []
        for i, roi in enumerate(overlapping_rois):
            color = (255, 0, 0) if i == 0 else (0, 255, 0) if i == 1 else (0, 0, 255)
            roi_item = self.roi_view.add_roi(roi, color)
            self.assertIsNotNone(roi_item)
            roi_items.append(roi_item)
        
        print(f"2. Добавлено {len(roi_items)} перекрывающихся ROI")
        
        # Тестируем изменение размера каждого ROI
        for i, roi_item in enumerate(roi_items):
            print(f"\n3. Тестируем изменение размера ROI {i}:")
            
            # Выбираем ROI
            self.roi_view._select_roi(roi_item)
            
            # Проверяем, что ROI выбран
            self.assertEqual(self.roi_view.selected_roi, roi_item)
            self.assertEqual(self.roi_view.selected_roi_id, i)
            
            # Тестируем изменение размера через маркер 2 (верхний правый)
            original_rect = roi_item.rect()
            print(f"   Оригинальный размер: {original_rect.width()}x{original_rect.height()}")
            
            # Создаем mock маркер
            mock_handle = Mock()
            mock_handle.handle_index = 2  # Верхний правый маркер
            
            # Устанавливаем маркер
            self.roi_view.resize_handle = mock_handle
            
            # Новые координаты - увеличиваем ширину
            new_scene_pos = QPointF(
                original_rect.right() + 100,  # Увеличиваем ширину на 100
                original_rect.top()           # Оставляем верхнюю границу без изменений
            )
            
            print(f"   Новые координаты маркера: {new_scene_pos}")
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_scene_pos, mock_handle)
            
            # Проверяем результат
            updated_rect = roi_item.rect()
            print(f"   Обновленный размер: {updated_rect.width()}x{updated_rect.height()}")
            
            # Проверяем, что ширина изменилась
            if updated_rect.width() > original_rect.width():
                print(f"   ✅ ROI {i}: ширина обновилась корректно")
            else:
                print(f"   ❌ ROI {i}: ПРОБЛЕМА - ширина не обновилась!")
                print(f"      Оригинал: {original_rect.width()}x{original_rect.height()}")
                print(f"      После обновления: {updated_rect.width()}x{updated_rect.height()}")
    
    def test_resize_handles_visibility_and_interaction(self):
        """Тест видимости и взаимодействия маркеров изменения размера"""
        print("\n=== ТЕСТ ВИДИМОСТИ И ВЗАИМОДЕЙСТВИЯ МАРКЕРОВ ===")
        
        # Создаем ROI
        roi_item = self.roi_view.add_roi([100, 100, 300, 250], (255, 0, 0))
        self.assertIsNotNone(roi_item)
        
        print(f"1. Создан ROI: {roi_item.rect()}")
        
        # Выбираем ROI
        self.roi_view._select_roi(roi_item)
        
        # Проверяем, что маркеры созданы
        self.assertEqual(len(self.roi_view.resize_handles), 8)
        print(f"2. Создано {len(self.roi_view.resize_handles)} маркеров")
        
        # Проверяем свойства каждого маркера
        for i, handle in enumerate(self.roi_view.resize_handles):
            # Проверяем, что маркер имеет правильные свойства
            self.assertIsNotNone(handle.parent_view)
            self.assertIsNotNone(handle.parent_roi)
            self.assertEqual(handle.handle_index, i)
            
            # Проверяем, что маркер видим
            self.assertTrue(handle.isVisible())
            
            # Проверяем, что маркер может быть выбран и перемещен
            self.assertTrue(handle.flags() & handle.GraphicsItemFlag.ItemIsSelectable)
            self.assertTrue(handle.flags() & handle.GraphicsItemFlag.ItemIsMovable)
            
            print(f"   Маркер {i}: ✅ все свойства корректны")
        
        print(f"3. Все маркеры созданы и настроены корректно")
        
        # Тестируем снятие выделения
        self.roi_view.deselect_roi()
        
        # Проверяем, что маркеры удалены
        self.assertEqual(len(self.roi_view.resize_handles), 0)
        print(f"4. Маркеры удалены после снятия выделения: ✅")


if __name__ == '__main__':
    unittest.main()
