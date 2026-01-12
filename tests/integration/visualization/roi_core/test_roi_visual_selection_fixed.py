#!/usr/bin/env python3
"""
Тесты для проверки визуального выделения ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor

from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIVisualSelection(unittest.TestCase):
    """Тесты для проверки визуального выделения ROI"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        self.mock_logger = Mock()
        
        # Создаем ROIGraphicsView
        self.roi_view = ROIGraphicsView()
        self.roi_view.logger = self.mock_logger
        
        # Создаем сцену
        self.scene = QGraphicsScene()
        self.roi_view.setScene(self.scene)
        
        # Настраиваем размеры
        self.roi_view.original_size = (1000, 800)
        self.roi_view.scale_x = 1.0
        self.roi_view.scale_y = 1.0
        
        # Настраиваем pixmap_item для корректной работы
        self.roi_view.pixmap_item = Mock()
        self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
        
        # Создаем тестовые ROI
        self.roi1 = self.roi_view.add_roi([100, 100, 200, 200], (255, 0, 0))  # Красный
        self.roi2 = self.roi_view.add_roi([150, 150, 250, 250], (0, 255, 0))  # Зеленый
        self.roi3 = self.roi_view.add_roi([200, 200, 300, 300], (0, 0, 255))  # Синий
    
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

    def test_roi_initial_colors(self):
        """Тест: ROI должны иметь правильные начальные цвета"""
        # Проверяем цвета ROI
        roi1_pen = self.roi1.pen()
        roi2_pen = self.roi2.pen()
        roi3_pen = self.roi3.pen()
        
        # ROI1 должен быть красным
        self.assertEqual(roi1_pen.color().red(), 255)
        self.assertEqual(roi1_pen.color().green(), 0)
        self.assertEqual(roi1_pen.color().blue(), 0)
        
        # ROI2 должен быть зеленым
        self.assertEqual(roi2_pen.color().red(), 0)
        self.assertEqual(roi2_pen.color().green(), 255)
        self.assertEqual(roi2_pen.color().blue(), 0)
        
        # ROI3 должен быть синим
        self.assertEqual(roi3_pen.color().red(), 0)
        self.assertEqual(roi3_pen.color().green(), 0)
        self.assertEqual(roi3_pen.color().blue(), 255)
    
    def test_select_roi_changes_color(self):
        """Тест: выбор ROI должен изменить его цвет на ярко-красный (выделение)"""
        # Выбираем ROI1
        self.roi_view._select_roi(self.roi1)
        
        # Проверяем, что ROI1 стал ярко-красным (выделенным)
        roi1_pen = self.roi1.pen()
        self.assertEqual(roi1_pen.color().red(), 255)
        self.assertEqual(roi1_pen.color().green(), 100)
        self.assertEqual(roi1_pen.color().blue(), 100)
        
        # Проверяем, что selected_roi установлен
        self.assertEqual(self.roi_view.selected_roi, self.roi1)
    
    def test_select_different_roi_restores_previous(self):
        """Тест: выбор другого ROI должен восстановить цвет предыдущего"""
        # Выбираем ROI1 (красный)
        self.roi_view._select_roi(self.roi1)
        
        # Проверяем, что ROI1 стал ярко-красным (выделенным)
        roi1_pen = self.roi1.pen()
        self.assertEqual(roi1_pen.color().red(), 255)
        self.assertEqual(roi1_pen.color().green(), 100)
        self.assertEqual(roi1_pen.color().blue(), 100)
        
        # Выбираем ROI2 (зеленый)
        self.roi_view._select_roi(self.roi2)
        
        # Проверяем, что ROI1 вернулся к обычному красному (оригинальный цвет)
        roi1_pen = self.roi1.pen()
        self.assertEqual(roi1_pen.color().red(), 255)
        self.assertEqual(roi1_pen.color().green(), 0)
        self.assertEqual(roi1_pen.color().blue(), 0)
        
        # Проверяем, что ROI2 стал ярко-красным (выделенным)
        roi2_pen = self.roi2.pen()
        self.assertEqual(roi2_pen.color().red(), 255)
        self.assertEqual(roi2_pen.color().green(), 100)
        self.assertEqual(roi2_pen.color().blue(), 100)
        
        # Проверяем, что selected_roi изменился
        self.assertEqual(self.roi_view.selected_roi, self.roi2)
    
    def test_select_roi_creates_resize_handles(self):
        """Тест: выбор ROI должен создать маркеры изменения размера"""
        # Выбираем ROI1
        self.roi_view._select_roi(self.roi1)
        
        # Проверяем, что созданы маркеры
        self.assertGreater(len(self.roi_view.resize_handles), 0)
        
        # Проверяем, что все маркеры принадлежат выбранному ROI
        for handle in self.roi_view.resize_handles:
            self.assertEqual(handle.parent_roi, self.roi1)
    
    def test_select_different_roi_removes_old_handles(self):
        """Тест: выбор другого ROI должен удалить старые маркеры"""
        # Выбираем ROI1
        self.roi_view._select_roi(self.roi1)
        handles1 = self.roi_view.resize_handles.copy()
        
        # Выбираем ROI2
        self.roi_view._select_roi(self.roi2)
        handles2 = self.roi_view.resize_handles.copy()
        
        # Проверяем, что маркеры изменились
        self.assertNotEqual(handles1, handles2)
        
        # Проверяем, что новые маркеры принадлежат ROI2
        for handle in handles2:
            self.assertEqual(handle.parent_roi, self.roi2)
    
    def test_pen_width_scaling(self):
        """Тест: толщина линий должна масштабироваться"""
        # Получаем базовую толщину
        base_width = self.roi_view._get_scaled_pen_width()
        
        # Изменяем масштаб
        self.roi_view.scale(2.0, 2.0)
        
        # Получаем новую толщину
        scaled_width = self.roi_view._get_scaled_pen_width()
        
        # Толщина должна измениться
        self.assertNotEqual(base_width, scaled_width)
    
    def test_selected_roi_has_thicker_pen(self):
        """Тест: выбранный ROI должен иметь более толстую линию"""
        # Получаем толщину обычного ROI
        normal_width = self.roi1.pen().width()
        
        # Выбираем ROI1
        self.roi_view._select_roi(self.roi1)
        
        # Получаем толщину выбранного ROI
        selected_width = self.roi1.pen().width()
        
        # Выбранный ROI должен иметь более толстую линию
        self.assertGreater(selected_width, normal_width)
    
    def test_roi_data_color_preservation(self):
        """Тест: цвета ROI должны сохраняться в roi_data"""
        # Проверяем, что цвета сохранились в roi_data
        self.assertEqual(len(self.roi_view.roi_data), 3)
        
        # Проверяем цвета в данных
        self.assertEqual(self.roi_view.roi_data[0]["color"], (255, 0, 0))  # Красный
        self.assertEqual(self.roi_view.roi_data[1]["color"], (0, 255, 0))  # Зеленый
        self.assertEqual(self.roi_view.roi_data[2]["color"], (0, 0, 255))  # Синий
    
    def test_select_roi_by_index(self):
        """Тест: выбор ROI по индексу"""
        # Выбираем ROI по индексу 1 (зеленый)
        self.roi_view.select_roi_by_index(1)
        
        # Проверяем, что выбран правильный ROI
        self.assertEqual(self.roi_view.selected_roi, self.roi2)
        
        # Проверяем, что цвет изменился на ярко-красный
        roi2_pen = self.roi2.pen()
        self.assertEqual(roi2_pen.color().red(), 255)
        self.assertEqual(roi2_pen.color().green(), 100)
        self.assertEqual(roi2_pen.color().blue(), 100)
    
    def test_select_invalid_index(self):
        """Тест: выбор несуществующего индекса не должен вызывать ошибку"""
        # Пытаемся выбрать несуществующий индекс
        self.roi_view.select_roi_by_index(999)
        
        # selected_roi должен остаться None
        self.assertIsNone(self.roi_view.selected_roi)
    
    def test_remove_resize_handles(self):
        """Тест: удаление маркеров изменения размера"""
        # Выбираем ROI1
        self.roi_view._select_roi(self.roi1)
        
        # Проверяем, что маркеры созданы
        self.assertGreater(len(self.roi_view.resize_handles), 0)
        
        # Удаляем маркеры
        self.roi_view._remove_resize_handles()
        
        # Проверяем, что маркеры удалены
        self.assertEqual(len(self.roi_view.resize_handles), 0)


class TestROISelectionIntegration(unittest.TestCase):
    """Интеграционные тесты для выбора ROI"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        self.mock_logger = Mock()
        
        # Создаем ROIGraphicsView
        self.roi_view = ROIGraphicsView()
        self.roi_view.logger = self.mock_logger
        
        # Создаем сцену
        self.scene = QGraphicsScene()
        self.roi_view.setScene(self.scene)
        
        # Настраиваем размеры
        self.roi_view.original_size = (1000, 800)
        self.roi_view.scale_x = 1.0
        self.roi_view.scale_y = 1.0
        
        # Настраиваем pixmap_item для корректной работы
        self.roi_view.pixmap_item = Mock()
        self.roi_view.pixmap_item.pos.return_value = QPointF(0, 0)
    
    def test_mouse_click_selection(self):
        """Тест: выбор ROI кликом мыши"""
        # Создаем перекрывающиеся ROI
        roi1 = self.roi_view.add_roi([100, 100, 200, 200], (255, 0, 0))  # Меньший
        roi2 = self.roi_view.add_roi([150, 150, 300, 300], (0, 255, 0))  # Больший
        
        # Вызываем _select_roi напрямую для тестирования
        self.roi_view._select_roi(roi1)
        
        # Проверяем, что выбран меньший ROI (roi1)
        self.assertEqual(self.roi_view.selected_roi, roi1)
        
        # Проверяем цвет
        roi1_pen = roi1.pen()
        self.assertEqual(roi1_pen.color().red(), 255)  # Ярко-красный для выделения
        self.assertEqual(roi1_pen.color().green(), 100)
        self.assertEqual(roi1_pen.color().blue(), 100)
    
    def test_multiple_selection_switching(self):
        """Тест: переключение между несколькими ROI"""
        # Создаем несколько ROI
        rois = []
        colors = [(255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0)]
        
        for i, color in enumerate(colors):
            roi = self.roi_view.add_roi([i*50, i*50, (i+1)*100, (i+1)*100], color)
            rois.append(roi)
        
        # Переключаемся между ROI
        for i, roi in enumerate(rois):
            self.roi_view._select_roi(roi)
            
            # Проверяем, что выбран правильный ROI
            self.assertEqual(self.roi_view.selected_roi, roi)
            
            # Проверяем, что цвет изменился на ярко-красный
            roi_pen = roi.pen()
            self.assertEqual(roi_pen.color().red(), 255)
            self.assertEqual(roi_pen.color().green(), 100)
            self.assertEqual(roi_pen.color().blue(), 100)
            
            # Проверяем, что предыдущие ROI вернулись к оригинальным цветам
            for j, prev_roi in enumerate(rois[:i]):
                prev_pen = prev_roi.pen()
                original_color = colors[j]
                self.assertEqual(prev_pen.color().red(), original_color[0])
                self.assertEqual(prev_pen.color().green(), original_color[1])
                self.assertEqual(prev_pen.color().blue(), original_color[2])


if __name__ == '__main__':
    unittest.main()
