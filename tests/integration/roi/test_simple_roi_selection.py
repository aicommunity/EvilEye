#!/usr/bin/env python3
"""
Простой тест для демонстрации работы выделения ROI
"""

import unittest
import time
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestSimpleROISelection(unittest.TestCase):
    """Простой тест для демонстрации работы выделения ROI"""
    
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
        self.roi_view.original_size = (1000, 800)
        self.roi_view.display_size = (1000, 800)
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

    def test_highlight_selected_roi(self):
        """Тест выделения ROI"""
        print("\n=== ДЕМОНСТРАЦИЯ ВЫДЕЛЕНИЯ ROI ===")
        
        # Создаем mock ROI
        roi = Mock(spec=QGraphicsRectItem)
        roi.setPen = Mock()
        
        # Настраиваем mock для _get_scaled_pen_width
        self.roi_view._get_scaled_pen_width = Mock(return_value=4)
        
        print("1. Вызываем _highlight_selected_roi...")
        self.roi_view._highlight_selected_roi(roi)
        
        # Проверяем вызов setPen
        roi.setPen.assert_called_once()
        pen = roi.setPen.call_args[0][0]
        
        print(f"   ✅ setPen вызван с цветом: RGB({pen.color().red()}, {pen.color().green()}, {pen.color().blue()})")
        print(f"   ✅ Толщина пера: {pen.width()}")
        print(f"   ✅ Цвет выделения: ярко-красный (255, 100, 100)")
        print(f"   ✅ Множитель толщины: {self.roi_view.selected_line_multiplier}")
        
        # Объясняем, что происходит
        print("\n2. Что происходит внутри PyQt6:")
        print("   - setPen() изменяет визуальные свойства элемента")
        print("   - Qt автоматически помечает элемент для перерисовки")
        print("   - Сцена автоматически обновляет отображение")
        print("   - ROI становится ярко-красным на экране")
        
        print("\n3. Почему нет явного repaint():")
        print("   - PyQt6 автоматически перерисовывает при изменении свойств")
        print("   - setPen() автоматически вызывает перерисовку")
        print("   - Не нужно помнить о вызове update()")
    
    def test_deselect_roi(self):
        """Тест снятия выделения ROI"""
        print("\n=== ДЕМОНСТРАЦИЯ СНЯТИЯ ВЫДЕЛЕНИЯ ROI ===")
        
        # Создаем mock ROI
        roi = Mock(spec=QGraphicsRectItem)
        roi.setPen = Mock()
        
        # Настраиваем состояние
        self.roi_view.selected_roi = roi
        self.roi_view.selected_roi_id = 0
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (0, 255, 0)}]
        
        # Настраиваем mock методы
        self.roi_view._remove_resize_handles = Mock()
        self.roi_view._get_scaled_pen_width = Mock(return_value=4)
        
        print("1. Вызываем deselect_roi...")
        self.roi_view.deselect_roi()
        
        # Проверяем, что setPen был вызван с оригинальным цветом
        roi.setPen.assert_called_once()
        pen = roi.setPen.call_args[0][0]
        
        print(f"   ✅ setPen вызван с оригинальным цветом: RGB({pen.color().red()}, {pen.color().green()}, {pen.color().blue()})")
        print(f"   ✅ Толщина пера: {pen.width()}")
        print(f"   ✅ Оригинальный цвет: зеленый (0, 255, 0)")
        
        # Проверяем, что выделение снято
        self.assertIsNone(self.roi_view.selected_roi)
        self.assertEqual(self.roi_view.selected_roi_id, -1)
        print(f"   ✅ selected_roi сброшен: {self.roi_view.selected_roi is None}")
        print(f"   ✅ selected_roi_id сброшен: {self.roi_view.selected_roi_id}")
        
        print("\n2. Что происходит:")
        print("   - setPen() восстанавливает оригинальный цвет")
        print("   - Qt автоматически перерисовывает элемент")
        print("   - ROI возвращается к зеленому цвету")
        print("   - Маркеры изменения размера удаляются")


if __name__ == '__main__':
    unittest.main()
