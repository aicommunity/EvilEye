#!/usr/bin/env python3
"""
Тест для проверки выбора вложенных ROI
"""


import unittest
import time
from unittest.mock import Mock, MagicMock, patch
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF, QRectF, QEvent
from PyQt6.QtGui import QPen, QColor

# Импортируем классы ROI редактора
from evileye.visualization_modules.roi_core import ROIGraphicsView

class TestNestedROISelection(unittest.TestCase):
    """Тест выбора вложенных ROI"""
    
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
        
        # Мокаем pixmap_item
        self.view.pixmap_item = Mock()
        self.view.pixmap_item.pos.return_value = QPointF(0, 0)
        self.view.original_size = (800, 600)
        
        # Создаем два вложенных ROI
        # Внешний ROI: [100, 100, 300, 300]
        # Внутренний ROI: [150, 150, 250, 250]
        self.outer_roi_coords = [100, 100, 300, 300]
        self.inner_roi_coords = [150, 150, 250, 250]
        
        # Добавляем ROI
        self.view.add_roi(self.outer_roi_coords, (255, 0, 0))  # Красный внешний
        self.view.add_roi(self.inner_roi_coords, (0, 255, 0))  # Зеленый внутренний
        
        self.outer_roi = self.view.rois[0]
        self.inner_roi = self.view.rois[1]
        
        print(f"\n=== Настройка теста ===")
        print(f"Внешний ROI: {self.outer_roi_coords}, zValue: {self.outer_roi.zValue()}")
        print(f"Внутренний ROI: {self.inner_roi_coords}, zValue: {self.inner_roi.zValue()}")
        print(f"Внутренний ROI должен иметь больший zValue: {self.inner_roi.zValue() > self.outer_roi.zValue()}")
    
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

    def test_z_order_setup(self):
        """Тест правильности установки z-order"""
        print(f"\n=== Тест z-order ===")
        print(f"Количество ROI: {len(self.view.rois)}")
        print(f"Внешний ROI zValue: {self.outer_roi.zValue()}")
        print(f"Внутренний ROI zValue: {self.inner_roi.zValue()}")
        
        # Внутренний ROI должен иметь больший zValue (быть сверху)
        self.assertGreater(self.inner_roi.zValue(), self.outer_roi.zValue())
    
    def test_nested_roi_selection(self):
        """Тест выбора вложенного ROI"""
        print(f"\n=== Тест выбора вложенного ROI ===")
        
        # Точка внутри внутреннего ROI (должна выбрать внутренний ROI)
        test_point = QPointF(200, 200)  # Центр внутреннего ROI
        
        # Мокаем scene.items() чтобы вернуть оба ROI
        mock_items = [self.inner_roi, self.outer_roi]  # В порядке от верхнего к нижнему
        with patch.object(self.view.scene, 'items', return_value=mock_items):
            # Мокаем mapToScene
            with patch.object(self.view, 'mapToScene', return_value=test_point):
                # Создаем мок события мыши
                mock_event = Mock()
                mock_event.button.return_value = Qt.MouseButton.LeftButton
                mock_event.pos.return_value = QPointF(200, 200)
                
                print(f"Тестовая точка: {test_point}")
                print(f"До выбора: selected_roi={self.view.selected_roi}")
                
                # Вызываем mousePressEvent
                self.view.mousePressEvent(mock_event)
                
                print(f"После выбора: selected_roi={self.view.selected_roi}")
                print(f"Выбранный ROI zValue: {self.view.selected_roi.zValue() if self.view.selected_roi else None}")
                
                # Проверяем, что выбран внутренний ROI
                self.assertEqual(self.view.selected_roi, self.inner_roi)
                self.assertEqual(self.view.selected_roi.zValue(), self.inner_roi.zValue())
    
    def test_outer_roi_selection(self):
        """Тест выбора внешнего ROI"""
        print(f"\n=== Тест выбора внешнего ROI ===")
        
        # Точка внутри внешнего ROI, но вне внутреннего
        test_point = QPointF(120, 120)  # Внешний ROI, но не внутренний
        
        # Мокаем scene.items() чтобы вернуть только внешний ROI
        mock_items = [self.outer_roi]
        with patch.object(self.view.scene, 'items', return_value=mock_items):
            # Мокаем mapToScene
            with patch.object(self.view, 'mapToScene', return_value=test_point):
                # Создаем мок события мыши
                mock_event = Mock()
                mock_event.button.return_value = Qt.MouseButton.LeftButton
                mock_event.pos.return_value = QPointF(120, 120)
                
                print(f"Тестовая точка: {test_point}")
                print(f"До выбора: selected_roi={self.view.selected_roi}")
                
                # Вызываем mousePressEvent
                self.view.mousePressEvent(mock_event)
                
                print(f"После выбора: selected_roi={self.view.selected_roi}")
                print(f"Выбранный ROI zValue: {self.view.selected_roi.zValue() if self.view.selected_roi else None}")
                
                # Проверяем, что выбран внешний ROI
                self.assertEqual(self.view.selected_roi, self.outer_roi)
                self.assertEqual(self.view.selected_roi.zValue(), self.outer_roi.zValue())
    
    def test_roi_items_filtering(self):
        """Тест фильтрации ROI элементов"""
        print(f"\n=== Тест фильтрации ROI элементов ===")
        
        # Создаем список элементов, включая не-ROI элементы
        mock_non_roi = Mock()
        mock_non_roi.__class__.__name__ = 'QGraphicsTextItem'
        
        all_items = [self.inner_roi, mock_non_roi, self.outer_roi]
        
        # Тестируем фильтрацию
        roi_items = [item for item in all_items if isinstance(item, type(self.outer_roi)) and item in self.view.rois]
        
        print(f"Все элементы: {len(all_items)}")
        print(f"ROI элементы: {len(roi_items)}")
        print(f"ROI элементы: {[item.zValue() for item in roi_items]}")
        
        # Проверяем, что фильтрация работает правильно
        self.assertEqual(len(roi_items), 2)
        self.assertIn(self.inner_roi, roi_items)
        self.assertIn(self.outer_roi, roi_items)
        self.assertNotIn(mock_non_roi, roi_items)
    
    def test_z_order_sorting(self):
        """Тест сортировки по z-order"""
        print(f"\n=== Тест сортировки по z-order ===")
        
        # Создаем список ROI в случайном порядке
        roi_items = [self.outer_roi, self.inner_roi]
        
        print(f"До сортировки: {[item.zValue() for item in roi_items]}")
        
        # Сортируем по z-order (по убыванию)
        roi_items.sort(key=lambda x: x.zValue(), reverse=True)
        
        print(f"После сортировки: {[item.zValue() for item in roi_items]}")
        
        # Проверяем, что внутренний ROI (с большим zValue) первый
        self.assertEqual(roi_items[0], self.inner_roi)
        self.assertEqual(roi_items[1], self.outer_roi)
        self.assertGreater(roi_items[0].zValue(), roi_items[1].zValue())


if __name__ == '__main__':
    # Создаем QApplication для тестов
    app = QApplication([])
    
    # Запускаем тесты
    unittest.main(verbosity=2)
