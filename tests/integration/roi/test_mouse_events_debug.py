#!/usr/bin/env python3
"""
Детальные тесты для отладки событий мыши при изменении размера ROI
"""


import unittest
import time
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QEvent
from PyQt6.QtGui import QPen, QColor

# Импортируем классы ROI редактора
from evileye.visualization_modules.roi_core import ROIGraphicsView

class TestMouseEventsDebug(unittest.TestCase):
    """Детальные тесты для отладки событий мыши"""
    
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
        
        # Создаем тестовый ROI
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        self.view.add_roi(coords, color)
        self.roi_item = self.view.rois[0]
        
        # Выбираем ROI и добавляем маркеры
        self.view._select_roi(self.roi_item)
        
        # Получаем маркер для тестирования (например, нижний правый угол)
        self.resize_handle = self.view.resize_handles[4]  # Нижний правый угол
    
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

    def test_resize_handle_properties(self):
        """Тест свойств маркера изменения размера"""
        print(f"\n=== Тест свойств маркера ===")
        print(f"Handle index: {self.resize_handle.handle_index}")
        print(f"Parent ROI: {self.resize_handle.parent_roi}")
        print(f"Handle position: {self.resize_handle.pos()}")
        print(f"Handle rect: {self.resize_handle.rect()}")
        print(f"Handle flags: {self.resize_handle.flags()}")
        print(f"Handle accepts hover events: {self.resize_handle.acceptHoverEvents()}")
        print(f"Handle zValue: {self.resize_handle.zValue()}")
        
        # Проверяем, что маркер правильно настроен
        self.assertEqual(self.resize_handle.handle_index, 4)
        self.assertEqual(self.resize_handle.parent_roi, self.roi_item)
        self.assertTrue(self.resize_handle.flags() & self.resize_handle.GraphicsItemFlag.ItemIsMovable)
        self.assertTrue(self.resize_handle.flags() & self.resize_handle.GraphicsItemFlag.ItemSendsGeometryChanges)
        self.assertTrue(self.resize_handle.acceptHoverEvents())
    
    def test_mouse_press_on_handle(self):
        """Тест нажатия мыши на маркер"""
        print(f"\n=== Тест нажатия мыши на маркер ===")
        
        # Создаем мок события мыши
        mock_event = Mock()
        mock_event.button.return_value = Qt.MouseButton.LeftButton
        mock_event.pos.return_value = QPointF(10, 10)  # Позиция относительно маркера
        
        # Мокаем setCursor
        with patch.object(self.resize_handle, 'setCursor') as mock_set_cursor:
            # Мокаем mapToScene
            with patch.object(self.resize_handle, 'mapToScene', return_value=QPointF(200, 200)):
                # Мокаем scene и views
                mock_scene = Mock()
                mock_view = Mock()
                mock_view._update_roi_size = Mock()
                mock_scene.views.return_value = [mock_view]
                self.resize_handle.scene = Mock(return_value=mock_scene)
                
                print(f"Before mousePressEvent: resizing={self.view.resizing}")
                print(f"Before mousePressEvent: resize_handle={self.view.resize_handle}")
                
                # Вызываем событие нажатия мыши
                self.resize_handle.mousePressEvent(mock_event)
                
                print(f"After mousePressEvent: resizing={self.view.resizing}")
                print(f"After mousePressEvent: resize_handle={self.view.resize_handle}")
                
                # Проверяем, что курсор изменился
                mock_set_cursor.assert_called()
                mock_event.accept.assert_called()
    
    def test_mouse_move_on_handle(self):
        """Тест движения мыши на маркере"""
        print(f"\n=== Тест движения мыши на маркере ===")
        
        # Создаем мок события мыши
        mock_event = Mock()
        mock_event.pos.return_value = QPointF(15, 15)  # Новая позиция
        
        # Мокаем mapToScene
        with patch.object(self.resize_handle, 'mapToScene', return_value=QPointF(210, 210)):
            # Мокаем scene и views
            mock_scene = Mock()
            mock_view = Mock()
            mock_view._update_roi_size = Mock()
            mock_scene.views.return_value = [mock_view]
            self.resize_handle.scene = Mock(return_value=mock_scene)
            
            print(f"Before mouseMoveEvent: ROI rect={self.roi_item.rect()}")
            
            # Вызываем событие движения мыши
            self.resize_handle.mouseMoveEvent(mock_event)
            
            print(f"After mouseMoveEvent: ROI rect={self.roi_item.rect()}")
            print(f"_update_roi_size called: {mock_view._update_roi_size.called}")
            
            # Проверяем, что _update_roi_size был вызван
            mock_view._update_roi_size.assert_called_with(QPointF(210, 210), self.resize_handle)
            mock_event.accept.assert_called()
    
    def test_mouse_release_on_handle(self):
        """Тест отпускания мыши на маркере"""
        print(f"\n=== Тест отпускания мыши на маркере ===")
        
        # Создаем мок события мыши
        mock_event = Mock()
        mock_event.button.return_value = Qt.MouseButton.LeftButton
        
        # Мокаем setCursor
        with patch.object(self.resize_handle, 'setCursor') as mock_set_cursor:
            print(f"Before mouseReleaseEvent: resizing={self.view.resizing}")
            
            # Вызываем событие отпускания мыши
            self.resize_handle.mouseReleaseEvent(mock_event)
            
            print(f"After mouseReleaseEvent: resizing={self.view.resizing}")
            
            # Проверяем, что курсор изменился обратно
            mock_set_cursor.assert_called()
            mock_event.accept.assert_called()
    
    def test_roi_size_update_logic(self):
        """Тест логики обновления размера ROI"""
        print(f"\n=== Тест логики обновления размера ROI ===")
        
        # Получаем текущий размер ROI
        original_rect = self.roi_item.rect()
        print(f"Original ROI rect: {original_rect}")
        
        # Тестируем обновление размера для разных маркеров
        test_cases = [
            (0, QPointF(50, 50), "Верхний левый"),
            (1, QPointF(150, 50), "Верхний центр"),
            (2, QPointF(250, 50), "Верхний правый"),
            (3, QPointF(250, 150), "Правый центр"),
            (4, QPointF(250, 250), "Нижний правый"),
            (5, QPointF(150, 250), "Нижний центр"),
            (6, QPointF(50, 250), "Нижний левый"),
            (7, QPointF(50, 150), "Левый центр"),
        ]
        
        for handle_index, new_pos, description in test_cases:
            print(f"\nТестируем {description} (handle_index={handle_index})")
            
            # Создаем мок маркера
            mock_handle = Mock()
            mock_handle.handle_index = handle_index
            
            # Вызываем _update_roi_size
            self.view._update_roi_size(new_pos, mock_handle)
            
            # Проверяем результат
            new_rect = self.roi_item.rect()
            print(f"  Новый rect: {new_rect}")
            print(f"  Изменился ли размер: {new_rect != original_rect}")
            
            # Восстанавливаем оригинальный размер для следующего теста
            self.roi_item.setRect(original_rect)
    
    def test_horizontal_vs_vertical_movement(self):
        """Тест горизонтального и вертикального движения"""
        print(f"\n=== Тест горизонтального и вертикального движения ===")
        
        original_rect = self.roi_item.rect()
        print(f"Original ROI rect: {original_rect}")
        
        # Тестируем горизонтальное движение (правый центр)
        print(f"\nТестируем горизонтальное движение (правый центр)")
        mock_handle_horizontal = Mock()
        mock_handle_horizontal.handle_index = 3  # Правый центр
        
        # Движение вправо
        horizontal_pos = QPointF(300, 150)  # Только X изменяется
        self.view._update_roi_size(horizontal_pos, mock_handle_horizontal)
        horizontal_rect = self.roi_item.rect()
        print(f"  После горизонтального движения: {horizontal_rect}")
        print(f"  Ширина изменилась: {horizontal_rect.width() != original_rect.width()}")
        print(f"  Высота изменилась: {horizontal_rect.height() != original_rect.height()}")
        
        # Восстанавливаем размер
        self.roi_item.setRect(original_rect)
        
        # Тестируем вертикальное движение (нижний центр)
        print(f"\nТестируем вертикальное движение (нижний центр)")
        mock_handle_vertical = Mock()
        mock_handle_vertical.handle_index = 5  # Нижний центр
        
        # Движение вниз
        vertical_pos = QPointF(150, 300)  # Только Y изменяется
        self.view._update_roi_size(vertical_pos, mock_handle_vertical)
        vertical_rect = self.roi_item.rect()
        print(f"  После вертикального движения: {vertical_rect}")
        print(f"  Ширина изменилась: {vertical_rect.width() != original_rect.width()}")
        print(f"  Высота изменилась: {vertical_rect.height() != original_rect.height()}")
    
    def test_multiple_mouse_moves(self):
        """Тест множественных движений мыши"""
        print(f"\n=== Тест множественных движений мыши ===")
        
        original_rect = self.roi_item.rect()
        print(f"Original ROI rect: {original_rect}")
        
        # Создаем мок маркера
        mock_handle = Mock()
        mock_handle.handle_index = 4  # Нижний правый угол
        
        # Симулируем несколько движений мыши
        movements = [
            QPointF(210, 210),  # Первое движение
            QPointF(220, 220),  # Второе движение
            QPointF(230, 230),  # Третье движение
        ]
        
        for i, pos in enumerate(movements):
            print(f"\nДвижение {i+1}: {pos}")
            self.view._update_roi_size(pos, mock_handle)
            current_rect = self.roi_item.rect()
            print(f"  ROI rect после движения: {current_rect}")
            print(f"  Размер изменился: {current_rect != original_rect}")
    
    def test_resize_handle_detection(self):
        """Тест определения маркера при клике"""
        print(f"\n=== Тест определения маркера при клике ===")
        
        # Тестируем клик на разных маркерах
        for i, handle in enumerate(self.view.resize_handles):
            print(f"\nМаркер {i}:")
            print(f"  Позиция: {handle.pos()}")
            print(f"  Rect: {handle.rect()}")
            print(f"  Handle index: {handle.handle_index}")
            print(f"  Parent ROI: {handle.parent_roi == self.roi_item}")
            
            # Проверяем, что маркер правильно настроен
            self.assertEqual(handle.handle_index, i)
            self.assertEqual(handle.parent_roi, self.roi_item)


class TestMouseEventsIntegration(unittest.TestCase):
    """Интеграционные тесты событий мыши"""
    
    def setUp(self):
        """Настройка перед каждым тестом"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        self.scene = QGraphicsScene()
        self.view = ROIGraphicsView()
        self.view.setScene(self.scene)
        self.view.logger = Mock()
        
        # Создаем тестовый ROI
        coords = [100, 100, 200, 200]
        color = (255, 0, 0)
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        self.view.add_roi(coords, color)
        self.roi_item = self.view.rois[0]
        self.view._select_roi(self.roi_item)
    
    def test_complete_resize_workflow(self):
        """Тест полного процесса изменения размера"""
        print(f"\n=== Тест полного процесса изменения размера ===")
        
        original_rect = self.roi_item.rect()
        print(f"Original ROI rect: {original_rect}")
        
        # Получаем маркер нижнего правого угла
        bottom_right_handle = self.view.resize_handles[4]
        print(f"Bottom right handle: {bottom_right_handle.handle_index}")
        
        # Симулируем полный процесс изменения размера
        print(f"\n1. Начальное состояние:")
        print(f"   resizing: {self.view.resizing}")
        print(f"   resize_handle: {self.view.resize_handle}")
        
        # Нажатие мыши
        print(f"\n2. Нажатие мыши на маркер:")
        # Мокаем события мыши
        with patch.object(bottom_right_handle, 'mousePressEvent') as mock_press:
            with patch.object(bottom_right_handle, 'mouseMoveEvent') as mock_move:
                with patch.object(bottom_right_handle, 'mouseReleaseEvent') as mock_release:
                    
                    # Симулируем нажатие
                    mock_press_event = Mock()
                    mock_press_event.button.return_value = Qt.MouseButton.LeftButton
                    mock_press_event.pos.return_value = QPointF(10, 10)
                    
                    # Вызываем нажатие
                    bottom_right_handle.mousePressEvent(mock_press_event)
                    
                    print(f"   После нажатия: resizing={self.view.resizing}")
                    
                    # Симулируем движение
                    mock_move_event = Mock()
                    mock_move_event.pos.return_value = QPointF(20, 20)
                    
                    # Мокаем mapToScene и scene
                    with patch.object(bottom_right_handle, 'mapToScene', return_value=QPointF(250, 250)):
                        mock_scene = Mock()
                        mock_view = Mock()
                        mock_view._update_roi_size = Mock()
                        mock_scene.views.return_value = [mock_view]
                        bottom_right_handle.scene = Mock(return_value=mock_scene)
                        
                        # Вызываем движение
                        bottom_right_handle.mouseMoveEvent(mock_move_event)
                        
                        print(f"   После движения: _update_roi_size вызван={mock_view._update_roi_size.called}")
                        if mock_view._update_roi_size.called:
                            call_args = mock_view._update_roi_size.call_args
                            print(f"   Аргументы вызова: {call_args}")
                    
                    # Симулируем отпускание
                    mock_release_event = Mock()
                    mock_release_event.button.return_value = Qt.MouseButton.LeftButton
                    
                    # Вызываем отпускание
                    bottom_right_handle.mouseReleaseEvent(mock_release_event)
                    
                    print(f"   После отпускания: resizing={self.view.resizing}")


if __name__ == '__main__':
    # Создаем QApplication для тестов
    app = QApplication([])
    
    # Запускаем тесты
    unittest.main(verbosity=2)
