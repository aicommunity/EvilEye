#!/usr/bin/env python3
"""
Базовый тест для проверки создания и показа ROI редактора
"""

import unittest
from unittest.mock import Mock, patch
import time

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QPointF, QTimer
from PyQt6.QtGui import QPixmap
import cv2
import numpy as np

# Импортируем модули
from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


class TestROIEditorBasic(unittest.TestCase):
    """Базовый тест для проверки ROI редактора"""
    
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
    
    def test_roi_editor_creation(self):
        """Тест создания ROI редактора"""
        print("\n=== ТЕСТ СОЗДАНИЯ ROI РЕДАКТОРА ===")
        
        # Проверяем, что окно создано
        self.assertIsNotNone(self.roi_window)
        print("   ✅ ROI редактор создан")
        
        # Проверяем, что canvas создан
        self.assertIsNotNone(self.roi_window.roi_canvas)
        print("   ✅ ROI canvas создан")
        
        # Проверяем, что список ROI создан
        self.assertIsNotNone(self.roi_window.roi_list)
        print("   ✅ ROI список создан")
    
    def test_set_cv_image(self):
        """Тест установки изображения"""
        print("\n=== ТЕСТ УСТАНОВКИ ИЗОБРАЖЕНИЯ ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)  # Синий цвет
        
        print("1. Создано тестовое изображение 640x480")
        
        # Устанавливаем изображение
        try:
            self.roi_window.set_cv_image(0, test_image)
            print("   ✅ Изображение установлено без ошибок")
        except Exception as e:
            self.fail(f"Ошибка при установке изображения: {e}")
        
        # Проверяем, что pixmap_item создан
        self.assertIsNotNone(self.roi_window.roi_canvas.pixmap_item)
        print("   ✅ Pixmap item создан")
        
        # Проверяем размеры
        self.assertIsNotNone(self.roi_window.roi_canvas.original_size)
        print(f"   ✅ Оригинальный размер: {self.roi_window.roi_canvas.original_size}")
    
    def test_set_rois_from_detector_basic(self):
        """Базовый тест установки ROI из детектора"""
        print("\n=== ТЕСТ УСТАНОВКИ ROI ИЗ ДЕТЕКТОРА ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        self.roi_window.set_cv_image(0, test_image)
        
        # Тестовые ROI в формате [x, y, w, h]
        test_rois = [
            [100, 100, 200, 150],
            [300, 200, 150, 100]
        ]
        
        print(f"1. Устанавливаем {len(test_rois)} ROI из детектора")
        
        # Устанавливаем ROI
        try:
            self.roi_window.set_rois_from_detector(test_rois)
            print("   ✅ ROI установлены без ошибок")
        except Exception as e:
            self.fail(f"Ошибка при установке ROI: {e}")
        
        # Проверяем, что ROI добавлены
        self.assertEqual(len(self.roi_window.roi_canvas.rois), 2)
        self.assertEqual(len(self.roi_window.roi_canvas.roi_data), 2)
        print(f"   ✅ ROI добавлены: {len(self.roi_window.roi_canvas.rois)} ROI(s)")
        
        # Проверяем, что список обновлен
        self.assertEqual(self.roi_window.roi_list.count(), 2)
        print(f"   ✅ Список ROI обновлен: {self.roi_window.roi_list.count()} элементов")
    
    def test_window_visibility(self):
        """Тест видимости окна"""
        print("\n=== ТЕСТ ВИДИМОСТИ ОКНА ===")
        
        # Проверяем, что окно может быть показано
        try:
            self.roi_window.setVisible(True)
            print("   ✅ Окно установлено как видимое")
        except Exception as e:
            self.fail(f"Ошибка при показе окна: {e}")
        
        # Проверяем, что окно может быть скрыто
        try:
            self.roi_window.setVisible(False)
            print("   ✅ Окно установлено как скрытое")
        except Exception as e:
            self.fail(f"Ошибка при скрытии окна: {e}")


if __name__ == '__main__':
    unittest.main()

