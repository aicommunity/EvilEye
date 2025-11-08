#!/usr/bin/env python3
"""
Простой тест для проверки проблемы с обновлением линий ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIResizeSimple(unittest.TestCase):
    """Простой тест для проверки проблемы с обновлением линий ROI"""
    
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

    def test_update_roi_size_direct_call(self):
        """Тест прямого вызова _update_roi_size"""
        print("\n=== ТЕСТ ПРЯМОГО ВЫЗОВА _update_roi_size ===")
        
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
        print(f"   selected_roi установлен: {self.roi_view.selected_roi}")
        
        # Создаем mock маркер
        mock_handle = Mock()
        mock_handle.handle_index = 4  # Нижний правый маркер
        
        # Устанавливаем маркер
        self.roi_view.resize_handle = mock_handle
        
        print(f"2. Установлен resize_handle: {self.roi_view.resize_handle}")
        print(f"   handle_index: {mock_handle.handle_index}")
        
        # Новые координаты
        new_scene_pos = QPointF(350, 250)
        
        print(f"3. Вызываем _update_roi_size с позицией: {new_scene_pos}")
        
        # Вызываем _update_roi_size напрямую
        self.roi_view._update_roi_size(new_scene_pos, mock_handle)
        
        # Проверяем результат
        updated_rect = roi_item.rect()
        print(f"4. После _update_roi_size: {updated_rect}")
        
        # Проверяем, что размер изменился
        if updated_rect.width() > 200 or updated_rect.height() > 150:
            print(f"   ✅ ROI изменился корректно")
        else:
            print(f"   ❌ ПРОБЛЕМА: ROI не изменился!")
    
    def test_update_roi_size_without_handle(self):
        """Тест _update_roi_size без маркера"""
        print("\n=== ТЕСТ _update_roi_size БЕЗ МАРКЕРА ===")
        
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
        
        # НЕ устанавливаем resize_handle
        self.roi_view.resize_handle = None
        
        print(f"1. Создан ROI: {roi_item.rect()}")
        print(f"   selected_roi установлен: {self.roi_view.selected_roi}")
        print(f"   resize_handle: {self.roi_view.resize_handle}")
        
        # Новые координаты
        new_scene_pos = QPointF(350, 250)
        
        print(f"2. Вызываем _update_roi_size с позицией: {new_scene_pos}")
        
        # Вызываем _update_roi_size без маркера
        self.roi_view._update_roi_size(new_scene_pos, None)
        
        # Проверяем результат
        updated_rect = roi_item.rect()
        print(f"3. После _update_roi_size: {updated_rect}")
        
        # Должно быть предупреждение в логах
        print(f"   Ожидается предупреждение о отсутствии маркера")
    
    def test_update_roi_size_without_selected_roi(self):
        """Тест _update_roi_size без выбранного ROI"""
        print("\n=== ТЕСТ _update_roi_size БЕЗ ВЫБРАННОГО ROI ===")
        
        # НЕ устанавливаем selected_roi
        self.roi_view.selected_roi = None
        self.roi_view.selected_roi_id = -1
        
        # Создаем mock маркер
        mock_handle = Mock()
        mock_handle.handle_index = 4
        
        # Устанавливаем маркер
        self.roi_view.resize_handle = mock_handle
        
        print(f"1. selected_roi: {self.roi_view.selected_roi}")
        print(f"   resize_handle: {self.roi_view.resize_handle}")
        
        # Новые координаты
        new_scene_pos = QPointF(350, 250)
        
        print(f"2. Вызываем _update_roi_size с позицией: {new_scene_pos}")
        
        # Вызываем _update_roi_size без выбранного ROI
        self.roi_view._update_roi_size(new_scene_pos, mock_handle)
        
        print(f"3. Ожидается предупреждение о отсутствии выбранного ROI")


if __name__ == '__main__':
    unittest.main()
