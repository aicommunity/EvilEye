#!/usr/bin/env python3
"""
Тест для проверки исправления зависания при загрузке ROI
"""

import unittest
import time
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPixmap
import cv2
import numpy as np

# Импортируем модули
from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


class TestROILoadingFix(unittest.TestCase):
    """Тест для проверки исправления зависания при загрузке ROI"""
    
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
        """Тест, что set_rois_from_detector не зависает с исправлениями"""
        print("\n=== ТЕСТ set_rois_from_detector БЕЗ ЗАВИСАНИЯ (ИСПРАВЛЕННЫЙ) ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        self.roi_window.set_cv_image(0, test_image)
        
        # Тестовые ROI в формате [x, y, w, h]
        test_rois = [
            [100, 100, 200, 150],
            [300, 200, 150, 100],
            [500, 300, 100, 80]
        ]
        
        print(f"1. Загружаем {len(test_rois)} ROI из детектора")
        
        # Вызываем метод - не должно быть исключений или зависания
        try:
            self.roi_window.set_rois_from_detector(test_rois)
            print("   ✅ Метод выполнен без зависания")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что ROI добавлены
        self.assertEqual(len(self.roi_window.roi_canvas.rois), 3)
        self.assertEqual(len(self.roi_window.roi_canvas.roi_data), 3)
        print(f"   ✅ ROI добавлены: {len(self.roi_window.roi_canvas.rois)} ROI(s)")
        
        # Проверяем, что список обновлен
        self.assertEqual(self.roi_window.roi_list.count(), 3)
        print(f"   ✅ Список ROI обновлен: {self.roi_window.roi_list.count()} элементов")
    
    def test_set_rois_from_detector_with_large_dataset(self):
        """Тест с большим количеством ROI"""
        print("\n=== ТЕСТ С БОЛЬШИМ КОЛИЧЕСТВОМ ROI ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        self.roi_window.set_cv_image(0, test_image)
        
        # Создаем много ROI
        test_rois = []
        for i in range(10):
            x = 50 + i * 50
            y = 50 + i * 30
            w = 100
            h = 80
            test_rois.append([x, y, w, h])
        
        print(f"1. Загружаем {len(test_rois)} ROI из детектора")
        
        # Вызываем метод - не должно быть зависания
        try:
            self.roi_window.set_rois_from_detector(test_rois)
            print("   ✅ Метод выполнен без зависания")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что все ROI добавлены
        self.assertEqual(len(self.roi_window.roi_canvas.rois), 10)
        self.assertEqual(len(self.roi_window.roi_canvas.roi_data), 10)
        print(f"   ✅ Все ROI добавлены: {len(self.roi_window.roi_canvas.rois)} ROI(s)")
    
    def test_set_rois_from_detector_with_invalid_data(self):
        """Тест с некорректными данными"""
        print("\n=== ТЕСТ С НЕКОРРЕКТНЫМИ ДАННЫМИ ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        self.roi_window.set_cv_image(0, test_image)
        
        # Некорректные данные ROI
        invalid_rois = [
            [100, 100, 200, 150],  # Валидный
            [300, 200, 0, 100],    # Некорректный: w=0
            [500, 300, 100, 0],    # Некорректный: h=0
            [700, 400, 50, 30],    # Валидный
            []                     # Пустой список
        ]
        
        print(f"1. Загружаем {len(invalid_rois)} ROI (некоторые некорректные)")
        
        # Вызываем метод - не должно быть зависания
        try:
            self.roi_window.set_rois_from_detector(invalid_rois)
            print("   ✅ Метод выполнен без зависания")
        except Exception as e:
            self.fail(f"Метод set_rois_from_detector вызвал исключение: {e}")
        
        # Проверяем, что добавлены только валидные ROI
        self.assertEqual(len(self.roi_window.roi_canvas.rois), 2)
        self.assertEqual(len(self.roi_window.roi_canvas.roi_data), 2)
        print(f"   ✅ Добавлены только валидные ROI: {len(self.roi_window.roi_canvas.rois)} ROI(s)")


if __name__ == '__main__':
    unittest.main()

