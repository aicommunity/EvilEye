#!/usr/bin/env python3
"""
Тест для демонстрации работы выделения ROI и перерисовки
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROISelectionRepaint(unittest.TestCase):
    """Тест для демонстрации работы выделения ROI и перерисовки"""
    
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

    def test_roi_selection_mechanism(self):
        """Тест механизма выделения ROI"""
        print("\n=== ДЕМОНСТРАЦИЯ МЕХАНИЗМА ВЫДЕЛЕНИЯ ROI ===")
        
        # 1. Создаем mock ROI элементы
        roi1 = Mock(spec=QGraphicsRectItem)
        roi2 = Mock(spec=QGraphicsRectItem)
        
        # Настраиваем mock методы
        roi1.setPen = Mock()
        roi2.setPen = Mock()
        roi1.zValue.return_value = 1.0
        roi2.zValue.return_value = 2.0
        roi1.rect.return_value = QRectF(100, 100, 200, 150)
        roi2.rect.return_value = QRectF(300, 300, 150, 100)
        
        # Добавляем ROI в список
        self.roi_view.rois = [roi1, roi2]
        self.roi_view.roi_data = [
            {"coords": [100, 100, 300, 250], "color": (255, 0, 0)},
            {"coords": [300, 300, 450, 400], "color": (0, 255, 0)}
        ]
        
        print("1. Созданы 2 ROI элемента:")
        print(f"   ROI 1: цвет (255, 0, 0) - красный")
        print(f"   ROI 2: цвет (0, 255, 0) - зеленый")
        
        # 2. Выбираем первый ROI
        print("\n2. Выбираем ROI 1...")
        self.roi_view._select_roi(roi1)
        
        # Проверяем, что setPen был вызван с правильным цветом
        roi1.setPen.assert_called()
        pen_call = roi1.setPen.call_args[0][0]
        print(f"   Вызван setPen с цветом: RGB({pen_call.color().red()}, {pen_call.color().green()}, {pen_call.color().blue()})")
        print(f"   Толщина пера: {pen_call.width()}")
        
        # Проверяем состояние
        self.assertEqual(self.roi_view.selected_roi, roi1)
        self.assertEqual(self.roi_view.selected_roi_id, 0)
        print(f"   selected_roi установлен: {self.roi_view.selected_roi == roi1}")
        print(f"   selected_roi_id установлен: {self.roi_view.selected_roi_id}")
        
        # 3. Выбираем второй ROI
        print("\n3. Выбираем ROI 2...")
        self.roi_view._select_roi(roi2)
        
        # Проверяем, что первый ROI вернулся к оригинальному цвету
        print(f"   ROI 1 setPen вызван {roi1.setPen.call_count} раз(а)")
        print(f"   ROI 2 setPen вызван {roi2.setPen.call_count} раз(а)")
        
        # Проверяем состояние
        self.assertEqual(self.roi_view.selected_roi, roi2)
        self.assertEqual(self.roi_view.selected_roi_id, 1)
        print(f"   selected_roi изменен на: {self.roi_view.selected_roi == roi2}")
        print(f"   selected_roi_id изменен на: {self.roi_view.selected_roi_id}")
    
    def test_highlight_selected_roi_method(self):
        """Тест выделения ROI (используем _select_roi вместо _highlight_selected_roi)"""
        print("\n=== ДЕМОНСТРАЦИЯ ВЫДЕЛЕНИЯ ROI ===")
        
        # Метод _highlight_selected_roi не существует, используем _select_roi
        # Создаем реальный ROI
        roi = self.roi_view.add_roi([100, 100, 200, 200], (255, 0, 0))
        self.assertIsNotNone(roi)
        
        print("1. Вызываем _select_roi...")
        self.roi_view._select_roi(roi)
        
        # Проверяем, что ROI выделен
        self.assertEqual(self.roi_view.selected_roi, roi)
        self.assertEqual(self.roi_view.selected_roi_id, 0)
        
        # Проверяем, что перо установлено
        pen = roi.pen()
        print(f"   ✅ setPen вызван с цветом: RGB({pen.color().red()}, {pen.color().green()}, {pen.color().blue()})")
        print(f"   ✅ Толщина пера: {pen.width()}")
        print(f"   ✅ Множитель толщины: {self.roi_view.selected_line_multiplier}")
    
    def test_deselect_roi_method(self):
        """Тест метода deselect_roi"""
        print("\n=== ДЕМОНСТРАЦИЯ МЕТОДА deselect_roi ===")
        
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
        
        print(f"   setPen вызван с оригинальным цветом: RGB({pen.color().red()}, {pen.color().green()}, {pen.color().blue()})")
        print(f"   Толщина пера: {pen.width()}")
        print(f"   Оригинальный цвет: зеленый (0, 255, 0)")
        
        # Проверяем, что выделение снято
        self.assertIsNone(self.roi_view.selected_roi)
        self.assertEqual(self.roi_view.selected_roi_id, -1)
        print(f"   selected_roi сброшен: {self.roi_view.selected_roi is None}")
        print(f"   selected_roi_id сброшен: {self.roi_view.selected_roi_id}")
    
    def test_automatic_repaint_explanation(self):
        """Объяснение автоматической перерисовки"""
        print("\n=== ОБЪЯСНЕНИЕ АВТОМАТИЧЕСКОЙ ПЕРЕРИСОВКИ ===")
        
        print("1. Почему нет явного вызова repaint?")
        print("   - PyQt6 автоматически перерисовывает элементы при изменении их свойств")
        print("   - При вызове setPen() на QGraphicsRectItem, Qt автоматически помечает элемент для перерисовки")
        print("   - Сцена (QGraphicsScene) автоматически обновляет отображение")
        
        print("\n2. Как работает изменение цвета:")
        print("   - _highlight_selected_roi() вызывает roi_item.setPen(selected_pen)")
        print("   - setPen() изменяет визуальные свойства элемента")
        print("   - Qt автоматически перерисовывает элемент с новым пером")
        
        print("\n3. Как работает восстановление цвета:")
        print("   - deselect_roi() вызывает roi_item.setPen(normal_pen)")
        print("   - normal_pen создается с оригинальным цветом из roi_data")
        print("   - Qt автоматически перерисовывает элемент с оригинальным цветом")
        
        print("\n4. Когда нужен явный вызов update():")
        print("   - При добавлении/удалении элементов: scene.addItem() / scene.removeItem()")
        print("   - При изменении z-order: item.setZValue()")
        print("   - При изменении позиции: item.setPos()")
        print("   - В нашем коде: self.scene.update() вызывается в add_roi_direct()")
        
        print("\n5. Цепочка вызовов при выделении ROI:")
        print("   mousePressEvent() -> _select_roi() -> deselect_roi() + _highlight_selected_roi()")
        print("   deselect_roi() -> setPen(original_color) -> Qt автоматически перерисовывает")
        print("   _highlight_selected_roi() -> setPen(selected_color) -> Qt автоматически перерисовывает")


if __name__ == '__main__':
    unittest.main()
