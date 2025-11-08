#!/usr/bin/env python3
"""
Тесты для методов ROI редактора
"""


import unittest
import time
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF
from PyQt6.QtGui import QPen, QColor

# Импортируем классы ROI редактора
from evileye.visualization_modules.roi_core import ROIGraphicsView

class TestROIGraphicsView(unittest.TestCase):
    """Тесты для класса ROIGraphicsView"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        self.scene = QGraphicsScene()
        self.view = ROIGraphicsView()
        self.view.setScene(self.scene)
        
        # Мокаем логгер
        self.view.logger = Mock()
    
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

    def test_init(self):
        """Тест инициализации ROIGraphicsView"""
        self.assertIsNotNone(self.view.roi_data)
        self.assertIsNotNone(self.view.rois)
        self.assertIsNotNone(self.view.resize_handles)
        self.assertEqual(self.view.base_line_width, 4)
        self.assertEqual(self.view.handle_size, 20)
        self.assertEqual(self.view.selected_line_multiplier, 2.0)
        self.assertFalse(self.view.user_scaled)
        self.assertTrue(self.view.auto_fit_enabled)
    
    def test_add_roi(self):
        """Тест добавления ROI"""
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)  # Красный цвет в формате RGB
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        initial_count = len(self.view.rois)
        self.view.add_roi(coords, color)
        
        # Проверяем, что ROI добавлен
        self.assertEqual(len(self.view.rois), initial_count + 1)
        self.assertEqual(len(self.view.roi_data), initial_count + 1)
        
        # Проверяем данные ROI
        roi_data = self.view.roi_data[-1]
        self.assertEqual(roi_data["coords"], coords)
        self.assertEqual(roi_data["color"], (255, 0, 0))
    
    def test_convert_source_to_display_coords(self):
        """Тест преобразования координат из исходных в отображаемые"""
        # Устанавливаем размеры изображения
        self.view.original_size = (800, 600)
        self.view.scale_x = 1.0
        self.view.scale_y = 1.0
        
        source_coords = [100, 100, 200, 200]
        display_coords = self.view._convert_source_to_display_coords(source_coords)
        
        # При масштабе 1.0 координаты должны совпадать
        self.assertEqual(display_coords, source_coords)
    
    def test_convert_display_to_source_coords(self):
        """Тест преобразования координат из отображаемых в исходные"""
        # Устанавливаем размеры изображения
        self.view.original_size = (800, 600)
        self.view.scale_x = 1.0
        self.view.scale_y = 1.0
        
        display_coords = [100, 100, 200, 200]
        source_coords = self.view._convert_display_to_source_coords(display_coords)
        
        # При масштабе 1.0 координаты должны совпадать
        self.assertEqual(source_coords, display_coords)
    
    def test_get_scaled_pen_width(self):
        """Тест расчета масштабированной толщины пера"""
        # Тест с базовой толщиной
        self.view.base_line_width = 4
        self.view.transform().reset()
        
        pen_width = self.view._get_scaled_pen_width()
        self.assertEqual(pen_width, 4)
        
        # Тест с масштабированием
        self.view.scale(2.0, 2.0)
        pen_width = self.view._get_scaled_pen_width()
        # При масштабе 2.0 толщина должна уменьшиться в 2 раза для сохранения визуальной толщины
        self.assertLess(pen_width, 4)
    
    def test_select_roi(self):
        """Тест выбора ROI"""
        # Создаем тестовый ROI
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)  # Красный цвет в формате RGB
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        self.view.add_roi(coords, color)
        roi_item = self.view.rois[0]
        
        # Выбираем ROI
        self.view._select_roi(roi_item)
        
        # Проверяем, что ROI выбран
        self.assertEqual(self.view.selected_roi, roi_item)
        self.assertIsNotNone(self.view.resize_handles)
        self.assertGreater(len(self.view.resize_handles), 0)
    
    def test_add_resize_handles(self):
        """Тест добавления маркеров изменения размера"""
        # Создаем тестовый ROI
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)  # Красный цвет в формате RGB
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        self.view.add_roi(coords, color)
        roi_item = self.view.rois[0]
        
        # Добавляем маркеры
        self.view._add_resize_handles(roi_item)
        
        # Проверяем, что маркеры созданы
        self.assertEqual(len(self.view.resize_handles), 8)  # 8 маркеров
        
        # Проверяем атрибуты маркеров
        for i, handle in enumerate(self.view.resize_handles):
            self.assertEqual(handle.handle_index, i)
            self.assertEqual(handle.parent_roi, roi_item)
    
    def test_update_roi_size(self):
        """Тест обновления размера ROI"""
        # Создаем тестовый ROI
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)  # Красный цвет в формате RGB
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        self.view.add_roi(coords, color)
        roi_item = self.view.rois[0]
        
        # Выбираем ROI и добавляем маркеры
        self.view._select_roi(roi_item)
        
        # Создаем мок маркера
        mock_handle = Mock()
        mock_handle.handle_index = 4  # Нижний правый угол
        self.view.resize_handle = mock_handle
        
        # Обновляем размер
        new_pos = QPointF(300, 300)
        self.view._update_roi_size(new_pos, mock_handle)
        
        # Проверяем, что размер изменился
        new_rect = roi_item.rect()
        self.assertEqual(new_rect.bottomRight(), new_pos)


class TestResizeHandle(unittest.TestCase):
    """Тесты для класса ResizeHandle"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        self.handle = ResizeHandle(100, 100, 20)
    
    def test_init(self):
        """Тест инициализации ResizeHandle"""
        self.assertEqual(self.handle.rect().width(), 20)
        self.assertEqual(self.handle.rect().height(), 20)
        self.assertTrue(self.handle.flags() & self.handle.GraphicsItemFlag.ItemIsSelectable)
        self.assertTrue(self.handle.flags() & self.handle.GraphicsItemFlag.ItemIsMovable)
        self.assertTrue(self.handle.flags() & self.handle.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.assertTrue(self.handle.acceptHoverEvents())
        self.assertEqual(self.handle.zValue(), 1000)
    
    def test_mouse_press_event(self):
        """Тест события нажатия мыши"""
        # Создаем реальное событие мыши
        from PyQt6.QtWidgets import QGraphicsSceneMouseEvent
        from PyQt6.QtCore import QEvent
        
        event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMousePress)
        event.setButton(Qt.MouseButton.LeftButton)
        
        # Мокаем setCursor
        with patch.object(self.handle, 'setCursor') as mock_set_cursor:
            self.handle.mousePressEvent(event)
            mock_set_cursor.assert_called_once()
    
    def test_mouse_release_event(self):
        """Тест события отпускания мыши"""
        # Создаем реальное событие мыши
        from PyQt6.QtWidgets import QGraphicsSceneMouseEvent
        from PyQt6.QtCore import QEvent
        
        event = QGraphicsSceneMouseEvent(QEvent.Type.GraphicsSceneMouseRelease)
        event.setButton(Qt.MouseButton.LeftButton)
        
        # Мокаем setCursor
        with patch.object(self.handle, 'setCursor') as mock_set_cursor:
            self.handle.mouseReleaseEvent(event)
            mock_set_cursor.assert_called_once()
    
    def test_hover_events(self):
        """Тест событий наведения мыши"""
        # Мокаем setCursor
        with patch.object(self.handle, 'setCursor') as mock_set_cursor:
            # Тест входа мыши
            self.handle.hoverEnterEvent(None)
            mock_set_cursor.assert_called()
            
            # Тест выхода мыши
            self.handle.hoverLeaveEvent(None)
            mock_set_cursor.assert_called()


class TestROIEditorDialog(unittest.TestCase):
    """Тесты для класса ROIEditorDialog"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Мокаем параметры
        self.mock_params = {
            'pipeline': {
                'detectors': [
                    {
                        'source_ids': [0],
                        'roi': [[100, 100, 200, 200], [300, 300, 400, 400]]
                    }
                ]
            }
        }
    
    def test_load_rois_from_config(self):
        """Тест загрузки ROI из конфигурации"""
        dialog = ROIEditorDialog()
        
        # Мокаем roi_canvas
        dialog.roi_canvas = Mock()
        dialog.roi_canvas.original_size = (800, 600)
        
        # Мокаем логгер
        dialog.logger = Mock()
        
        # Загружаем ROI
        rois = dialog.load_rois_from_config(self.mock_params, 0)
        
        # Проверяем результат
        self.assertEqual(len(rois), 2)
        # ROI преобразуются из [x, y, width, height] в [x1, y1, x2, y2]
        self.assertEqual(rois[0], [100, 100, 300, 300])  # [100, 100, 200, 200] -> [100, 100, 300, 300]
        self.assertEqual(rois[1], [300, 300, 700, 700])  # [300, 300, 400, 400] -> [300, 300, 700, 700]
    
    def test_set_rois_from_config(self):
        """Тест установки ROI из конфигурации"""
        dialog = ROIEditorDialog()
        
        # Мокаем roi_canvas
        dialog.roi_canvas = Mock()
        dialog.roi_canvas.original_size = (800, 600)
        dialog.roi_canvas.roi_data = []
        dialog.roi_canvas.add_roi_direct = Mock()
        dialog.roi_canvas.scene = Mock()
        dialog.roi_canvas.scene.sceneRect.return_value = Mock()
        dialog.roi_canvas.scene.sceneRect.return_value.x.return_value = 0
        dialog.roi_canvas.scene.sceneRect.return_value.y.return_value = 0
        
        # Мокаем логгер
        dialog.logger = Mock()
        
        # Устанавливаем ROI
        dialog.set_rois_from_config(0, self.mock_params)
        
        # Проверяем, что ROI добавлены
        self.assertEqual(len(dialog.roi_canvas.roi_data), 2)
        dialog.roi_canvas.add_roi_direct.assert_called()


class TestROIInteraction(unittest.TestCase):
    """Тесты взаимодействия с ROI"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        self.scene = QGraphicsScene()
        self.view = ROIGraphicsView()
        self.view.setScene(self.scene)
        self.view.logger = Mock()
    
    def test_nested_roi_selection(self):
        """Тест выбора вложенных ROI"""
        # Создаем два ROI - один внутри другого
        outer_coords = [100, 100, 300, 300]
        inner_coords = [150, 150, 250, 250]
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        # Добавляем ROI
        self.view.add_roi(outer_coords, (255, 0, 0))  # Красный
        self.view.add_roi(inner_coords, (0, 0, 255))  # Синий
        
        # Проверяем порядок ROI (последний добавленный должен быть сверху)
        self.assertEqual(len(self.view.rois), 2)
        inner_roi = self.view.rois[1]  # Внутренний ROI
        outer_roi = self.view.rois[0]  # Внешний ROI
        
        # Проверяем z-order
        self.assertGreater(inner_roi.zValue(), outer_roi.zValue())
    
    def test_roi_click_detection(self):
        """Тест определения клика по ROI"""
        # Создаем два ROI
        outer_coords = [100, 100, 300, 300]
        inner_coords = [150, 150, 250, 250]
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        # Добавляем ROI
        self.view.add_roi(outer_coords, (255, 0, 0))  # Красный
        self.view.add_roi(inner_coords, (0, 0, 255))  # Синий
        
        # Тестируем клик в центре внутреннего ROI
        click_pos = QPointF(200, 200)  # Центр внутреннего ROI
        
        # Мокаем itemsAt
        with patch.object(self.scene, 'items') as mock_items:
            # Возвращаем внутренний ROI первым (он должен быть выбран)
            mock_items.return_value = [self.view.rois[1], self.view.rois[0]]
            
            # Симулируем клик
            mock_event = Mock()
            mock_event.button.return_value = Qt.MouseButton.LeftButton
            mock_event.pos.return_value = click_pos
            
            with patch.object(self.view, 'mapToScene', return_value=click_pos):
                self.view.mousePressEvent(mock_event)
            
            # Проверяем, что выбран внутренний ROI
            self.assertEqual(self.view.selected_roi, self.view.rois[1])


if __name__ == '__main__':
    # Создаем QApplication для тестов
    app = QApplication([])
    
    # Запускаем тесты
    unittest.main()
