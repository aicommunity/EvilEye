#!/usr/bin/env python3
"""
Тест для проверки проблемы с маркером 6 (нижний левый)
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIResizeHandle6(unittest.TestCase):
    """Тест для проверки проблемы с маркером 6 (нижний левый)"""
    
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

    def test_handle_6_bottom_left_resize(self):
        """Тест изменения размера маркером 6 (нижний левый)"""
        print("\n=== ТЕСТ МАРКЕРА 6 (НИЖНИЙ ЛЕВЫЙ) ===")
        
        # Создаем реальный ROI
        roi_item = QGraphicsRectItem(QRectF(100, 100, 200, 150))
        roi_item.setPen(QPen(Qt.GlobalColor.red, 2))
        
        # Добавляем в scene
        self.roi_view.scene.addItem(roi_item)
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        # Устанавливаем выбранный ROI
        self.roi_view.selected_roi = roi_item
        self.roi_view.selected_roi_id = 0
        
        print(f"1. Создан ROI: {roi_item.rect()}")
        print(f"   Размер: {roi_item.rect().width()}x{roi_item.rect().height()}")
        
        # Создаем mock маркер 6 (нижний левый)
        mock_handle = Mock()
        mock_handle.handle_index = 6
        
        # Устанавливаем маркер
        self.roi_view.resize_handle = mock_handle
        
        print(f"2. Установлен маркер 6 (нижний левый)")
        
        # Новые координаты - сдвигаем влево и вниз
        new_scene_pos = QPointF(50, 300)
        
        print(f"3. Вызываем _update_roi_size с позицией: {new_scene_pos}")
        print(f"   Ожидается: левая граница = 50, нижняя граница = 300")
        
        # Вызываем _update_roi_size
        self.roi_view._update_roi_size(new_scene_pos, mock_handle)
        
        # Проверяем результат
        updated_rect = roi_item.rect()
        print(f"4. После _update_roi_size: {updated_rect}")
        print(f"   Размер: {updated_rect.width()}x{updated_rect.height()}")
        print(f"   Левая граница: {updated_rect.left()}")
        print(f"   Нижняя граница: {updated_rect.bottom()}")
        
        # Проверяем, что левая граница изменилась на 50
        if abs(updated_rect.left() - 50) < 1:
            print(f"   ✅ Левая граница изменилась корректно")
        else:
            print(f"   ❌ ПРОБЛЕМА: левая граница не изменилась! Ожидалось 50, получено {updated_rect.left()}")
        
        # Проверяем, что нижняя граница изменилась на 300
        if abs(updated_rect.bottom() - 300) < 1:
            print(f"   ✅ Нижняя граница изменилась корректно")
        else:
            print(f"   ❌ ПРОБЛЕМА: нижняя граница не изменилась! Ожидалось 300, получено {updated_rect.bottom()}")
        
        # Проверяем, что размер изменился
        if updated_rect.width() != 200 or updated_rect.height() != 150:
            print(f"   ✅ Размер ROI изменился")
        else:
            print(f"   ❌ ПРОБЛЕМА: размер ROI не изменился!")
    
    def test_all_handles_comparison(self):
        """Тест сравнения всех маркеров"""
        print("\n=== ТЕСТ СРАВНЕНИЯ ВСЕХ МАРКЕРОВ ===")
        
        # Создаем реальный ROI
        roi_item = QGraphicsRectItem(QRectF(100, 100, 200, 150))
        roi_item.setPen(QPen(Qt.GlobalColor.red, 2))
        
        # Добавляем в scene
        self.roi_view.scene.addItem(roi_item)
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        # Устанавливаем выбранный ROI
        self.roi_view.selected_roi = roi_item
        self.roi_view.selected_roi_id = 0
        
        original_rect = roi_item.rect()
        print(f"1. Оригинальный ROI: {original_rect}")
        
        # Тестируем все маркеры
        test_cases = [
            (0, QPointF(50, 50), "Верхний левый"),
            (1, QPointF(200, 50), "Верхний центр"),
            (2, QPointF(350, 50), "Верхний правый"),
            (3, QPointF(350, 175), "Правый центр"),
            (4, QPointF(350, 300), "Нижний правый"),
            (5, QPointF(200, 300), "Нижний центр"),
            (6, QPointF(50, 300), "Нижний левый"),
            (7, QPointF(50, 175), "Левый центр"),
        ]
        
        for handle_index, new_pos, description in test_cases:
            print(f"\n2. Тестируем маркер {handle_index} ({description}):")
            
            # Создаем mock маркер
            mock_handle = Mock()
            mock_handle.handle_index = handle_index
            
            # Устанавливаем маркер
            self.roi_view.resize_handle = mock_handle
            
            # Запоминаем текущий размер
            before_rect = roi_item.rect()
            
            # Вызываем _update_roi_size
            self.roi_view._update_roi_size(new_pos, mock_handle)
            
            # Проверяем результат
            after_rect = roi_item.rect()
            
            print(f"   До: {before_rect}")
            print(f"   После: {after_rect}")
            
            # Проверяем, что что-то изменилось
            if after_rect != before_rect:
                print(f"   ✅ Маркер {handle_index} работает")
            else:
                print(f"   ❌ ПРОБЛЕМА: маркер {handle_index} не работает!")


if __name__ == '__main__':
    unittest.main()
