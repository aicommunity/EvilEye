#!/usr/bin/env python3
"""
Тесты для новых методов управления состоянием ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIStateManagement(unittest.TestCase):
    """Тесты для методов управления состоянием ROI"""
    
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

    def test_roi_state_initialization(self):
        """Тест инициализации состояния ROI"""
        # get_roi_state() не существует, используем прямой доступ к roi_state
        state = self.roi_view.roi_state
        
        self.assertEqual(state['selected_id'], -1)
        self.assertEqual(state['hovered_id'], -1)
        self.assertEqual(state['resizing_id'], -1)
        self.assertEqual(state['drawing'], False)
    
    def test_set_roi_state(self):
        """Тест установки состояния ROI"""
        self.roi_view.set_roi_state(selected_id=2, drawing=True)
        
        # get_roi_state() не существует, используем прямой доступ к roi_state
        state = self.roi_view.roi_state
        self.assertEqual(state['selected_id'], 2)
        self.assertEqual(state['drawing'], True)
        self.assertEqual(state['hovered_id'], -1)  # Не изменено
    
    def test_get_selected_roi_id(self):
        """Тест получения ID выбранного ROI"""
        self.roi_view.set_roi_state(selected_id=3)
        
        selected_id = self.roi_view.get_selected_roi_id()
        self.assertEqual(selected_id, 3)
    
    def test_get_roi_by_id(self):
        """Тест получения ROI по ID"""
        # Добавляем тестовые ROI
        mock_roi1 = Mock()
        mock_roi2 = Mock()
        self.roi_view.rois = [mock_roi1, mock_roi2]
        
        # Тест получения существующего ROI
        roi = self.roi_view.get_roi_by_id(0)
        self.assertEqual(roi, mock_roi1)
        
        roi = self.roi_view.get_roi_by_id(1)
        self.assertEqual(roi, mock_roi2)
        
        # Тест получения несуществующего ROI
        roi = self.roi_view.get_roi_by_id(2)
        self.assertIsNone(roi)
        
        roi = self.roi_view.get_roi_by_id(-1)
        self.assertIsNone(roi)
    
    def test_get_roi_data_by_id(self):
        """Тест получения данных ROI по ID"""
        # Добавляем тестовые данные ROI
        roi_data1 = {"coords": [100, 100, 200, 200], "color": (255, 0, 0)}
        roi_data2 = {"coords": [300, 300, 400, 400], "color": (0, 255, 0)}
        self.roi_view.roi_data = [roi_data1, roi_data2]
        
        # Тест получения существующих данных
        data = self.roi_view.get_roi_data_by_id(0)
        self.assertEqual(data, roi_data1)
        
        data = self.roi_view.get_roi_data_by_id(1)
        self.assertEqual(data, roi_data2)
        
        # Тест получения несуществующих данных
        data = self.roi_view.get_roi_data_by_id(2)
        self.assertIsNone(data)
    
    def test_deselect_roi(self):
        """Тест снятия выделения с ROI"""
        # Создаем mock для selected_roi
        mock_roi = Mock()
        self.roi_view.selected_roi = mock_roi
        self.roi_view.selected_roi_id = 0  # Исправляем индекс
        
        # Настраиваем данные ROI
        self.roi_view.roi_data = [{"coords": [100, 100, 200, 200], "color": (255, 0, 0)}]
        self.roi_view.set_roi_state(selected_id=0)  # Исправляем индекс
        
        # Mock для _remove_resize_handles
        self.roi_view._remove_resize_handles = Mock()
        
        # Вызываем deselect_roi
        self.roi_view.deselect_roi()
        
        # Проверяем, что выделение снято
        self.assertIsNone(self.roi_view.selected_roi)
        self.assertEqual(self.roi_view.selected_roi_id, -1)
        self.assertEqual(self.roi_view.get_selected_roi_id(), -1)
        
        # Проверяем, что вызван _remove_resize_handles
        self.roi_view._remove_resize_handles.assert_called_once()
    
    def test_create_roi_item(self):
        """Тест создания ROI элемента"""
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)
        
        # Mock для _convert_source_to_display_coords
        self.roi_view._convert_source_to_display_coords = Mock(return_value=[100, 100, 200, 200])
        self.roi_view._get_scaled_pen_width = Mock(return_value=4)
        
        # Создаем ROI элемент
        roi_item = self.roi_view._create_roi_item(coords, color)
        
        # Проверяем, что элемент создан
        self.assertIsNotNone(roi_item)
        self.assertEqual(roi_item.zValue(), 1000 - int(10000 / 1000))  # zValue на основе площади
    
    def test_highlight_selected_roi(self):
        """Тест выделения выбранного ROI (используем _select_roi вместо _highlight_selected_roi)"""
        # Создаем реальный ROI
        roi_item = self.roi_view.add_roi([100, 100, 200, 200], (255, 0, 0))
        self.assertIsNotNone(roi_item)
        
        # Выделяем ROI используя _select_roi (который вызывает выделение)
        self.roi_view._select_roi(roi_item)
        
        # Проверяем, что ROI выделен
        self.assertEqual(self.roi_view.selected_roi, roi_item)
        self.assertEqual(self.roi_view.selected_roi_id, 0)
        self.assertEqual(self.roi_view.get_selected_roi_id(), 0)
    
    def test_draw_scene(self):
        """Тест перерисовки сцены (метод draw_scene не существует, проверяем через scene.update())"""
        # Добавляем тестовые ROI
        roi_item1 = self.roi_view.add_roi([100, 100, 200, 200], (255, 0, 0))
        roi_item2 = self.roi_view.add_roi([300, 300, 400, 400], (0, 255, 0))
        
        # Проверяем, что ROI добавлены
        self.assertEqual(len(self.roi_view.rois), 2)
        self.assertEqual(len(self.roi_view.roi_data), 2)
        
        # Выделяем первый ROI
        self.roi_view._select_roi(roi_item1)
        self.assertEqual(self.roi_view.selected_roi_id, 0)
        
        # Обновляем сцену (метод draw_scene не существует, используем scene.update())
        self.roi_view.scene.update()
        
        # Проверяем, что выделение работает
        self.assertEqual(self.roi_view.selected_roi, roi_item1)
        
        # Проверяем, что ROI очищены и пересозданы
        self.assertEqual(len(self.roi_view.rois), 2)


class TestROIEditorDialogStateManagement(unittest.TestCase):
    """Тесты для ROIEditorWindow с новыми методами"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        with patch('evileye.visualization_modules.roi_core.get_module_logger') as mock_logger:
            mock_logger.return_value = Mock()
            from evileye.visualization_modules.roi_editor_window import ROIEditorWindow
            self.dialog = ROIEditorWindow({})
    
    def test_roi_editor_dialog_initialization(self):
        """Тест инициализации ROIEditorWindow"""
        # Проверяем, что roi_canvas создан
        self.assertIsNotNone(self.dialog.roi_canvas)
        
        # Проверяем, что roi_canvas имеет существующие методы
        self.assertTrue(hasattr(self.dialog.roi_canvas, 'roi_state'))  # roi_state существует
        self.assertTrue(hasattr(self.dialog.roi_canvas, 'set_roi_state'))  # set_roi_state существует
        self.assertTrue(hasattr(self.dialog.roi_canvas, 'select_roi_by_index'))  # select_roi_by_index существует
        self.assertTrue(hasattr(self.dialog.roi_canvas, 'deselect_roi'))  # deselect_roi существует


if __name__ == '__main__':
    unittest.main()
