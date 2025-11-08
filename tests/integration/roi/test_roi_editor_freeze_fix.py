#!/usr/bin/env python3
"""
Тест для проверки исправления зависания ROI редактора
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_editor_window import ROIEditorWindow
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIEditorFreezeFix(unittest.TestCase):
    """Тест для проверки исправления зависания ROI редактора"""
    
    def setUp(self):
        """Настройка тестов"""
        self.app = QApplication.instance()
        if self.app is None:
            self.app = QApplication([])
        
        # Создаем mock для логгера
        with patch('evileye.visualization_modules.roi_editor_window.get_module_logger') as mock_logger:
            mock_logger.return_value = Mock()
            self.params = {}
            self.roi_window = ROIEditorWindow(self.params)
    
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

    def test_set_rois_from_detector_no_freeze(self):
        """Тест, что set_rois_from_detector не зависает"""
        print("\n=== ТЕСТ set_rois_from_detector БЕЗ ЗАВИСАНИЯ ===")
        
        # Настраиваем mock для roi_canvas
        self.roi_window.roi_canvas = Mock()
        self.roi_window.roi_canvas.clear_rois = Mock()
        self.roi_window.roi_canvas.roi_data = []
        self.roi_window.roi_canvas.add_roi_direct = Mock()
        self.roi_window.roi_canvas.scene = Mock()
        self.roi_window.roi_canvas.scene.update = Mock()
        self.roi_window.roi_canvas.update = Mock()
        self.roi_window.roi_canvas.ensure_rois_visible = Mock()
        self.roi_window.roi_canvas.get_rois = Mock(return_value=[])
        
        # Настраиваем mock для _update_roi_list
        self.roi_window._update_roi_list = Mock()
        
        # Тестовые данные ROI в формате [x, y, w, h]
        rois_xywh = [
            [100, 100, 200, 150],  # ROI 1
            [300, 200, 150, 100],  # ROI 2
            [500, 300, 100, 80]    # ROI 3
        ]
        
        print(f"1. Загружаем {len(rois_xywh)} ROI из детектора")
        
        # Вызываем метод - не должно быть исключений
        try:
            self.roi_window.set_rois_from_detector(rois_xywh)
            print("   ✅ Метод выполнен без исключений")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что методы были вызваны
        self.roi_window.roi_canvas.clear_rois.assert_called_once()
        print("   ✅ clear_rois() вызван")
        
        # Проверяем, что add_roi_direct был вызван для каждого ROI
        expected_calls = len(rois_xywh)
        actual_calls = self.roi_window.roi_canvas.add_roi_direct.call_count
        self.assertEqual(actual_calls, expected_calls)
        print(f"   ✅ add_roi_direct() вызван {actual_calls} раз(а)")
        
        # Проверяем, что _update_roi_list был вызван
        self.roi_window._update_roi_list.assert_called_once()
        print("   ✅ _update_roi_list() вызван")
        
        # Проверяем, что сцена обновлена
        self.roi_window.roi_canvas.scene.update.assert_called_once()
        self.roi_window.roi_canvas.update.assert_called_once()
        print("   ✅ Сцена обновлена")
    
    def test_set_rois_from_detector_with_invalid_data(self):
        """Тест обработки некорректных данных ROI"""
        print("\n=== ТЕСТ ОБРАБОТКИ НЕКОРРЕКТНЫХ ДАННЫХ ===")
        
        # Настраиваем mock для roi_canvas
        self.roi_window.roi_canvas = Mock()
        self.roi_window.roi_canvas.clear_rois = Mock()
        self.roi_window.roi_canvas.roi_data = []
        self.roi_window.roi_canvas.add_roi_direct = Mock()
        self.roi_window.roi_canvas.scene = Mock()
        self.roi_window.roi_canvas.scene.update = Mock()
        self.roi_window.roi_canvas.update = Mock()
        self.roi_window.roi_canvas.ensure_rois_visible = Mock()
        self.roi_window.roi_canvas.get_rois = Mock(return_value=[])
        
        # Настраиваем mock для _update_roi_list
        self.roi_window._update_roi_list = Mock()
        
        # Некорректные данные ROI
        invalid_rois = [
            [100, 100, 200, 150],  # Валидный ROI
            [300, 200, 0, 100],    # Некорректный: w=0
            [500, 300, 100, 0],    # Некорректный: h=0
            [700, 400, 50, 30],    # Валидный ROI
            []                     # Пустой список
        ]
        
        print(f"1. Загружаем {len(invalid_rois)} ROI (некоторые некорректные)")
        
        # Вызываем метод - не должно быть исключений
        try:
            self.roi_window.set_rois_from_detector(invalid_rois)
            print("   ✅ Метод выполнен без исключений")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что add_roi_direct был вызван только для валидных ROI
        # Ожидаем 2 вызова (только валидные ROI)
        expected_calls = 2
        actual_calls = self.roi_window.roi_canvas.add_roi_direct.call_count
        self.assertEqual(actual_calls, expected_calls)
        print(f"   ✅ add_roi_direct() вызван {actual_calls} раз(а) (только для валидных ROI)")
    
    def test_set_rois_from_detector_empty_data(self):
        """Тест обработки пустых данных ROI"""
        print("\n=== ТЕСТ ОБРАБОТКИ ПУСТЫХ ДАННЫХ ===")
        
        # Настраиваем mock для roi_canvas
        self.roi_window.roi_canvas = Mock()
        self.roi_window.roi_canvas.clear_rois = Mock()
        self.roi_window.roi_canvas.roi_data = []
        self.roi_window.roi_canvas.add_roi_direct = Mock()
        self.roi_window.roi_canvas.scene = Mock()
        self.roi_window.roi_canvas.scene.update = Mock()
        self.roi_window.roi_canvas.update = Mock()
        self.roi_window.roi_canvas.ensure_rois_visible = Mock()
        self.roi_window.roi_canvas.get_rois = Mock(return_value=[])
        
        # Настраиваем mock для _update_roi_list
        self.roi_window._update_roi_list = Mock()
        
        # Пустые данные
        empty_rois = []
        
        print("1. Загружаем пустой список ROI")
        
        # Вызываем метод - не должно быть исключений
        try:
            self.roi_window.set_rois_from_detector(empty_rois)
            print("   ✅ Метод выполнен без исключений")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что clear_rois был вызван
        self.roi_window.roi_canvas.clear_rois.assert_called_once()
        print("   ✅ clear_rois() вызван")
        
        # Проверяем, что add_roi_direct НЕ был вызван
        self.roi_window.roi_canvas.add_roi_direct.assert_not_called()
        print("   ✅ add_roi_direct() НЕ вызван (нет ROI для добавления)")
        
        # Проверяем, что _update_roi_list был вызван
        self.roi_window._update_roi_list.assert_called_once()
        print("   ✅ _update_roi_list() вызван")


if __name__ == '__main__':
    unittest.main()

