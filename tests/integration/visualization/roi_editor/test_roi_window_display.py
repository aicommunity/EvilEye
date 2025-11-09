#!/usr/bin/env python3
"""
Тест для проверки правильного отображения ROI окна
"""

import unittest
from unittest.mock import Mock, patch
import time

from PyQt6.QtWidgets import QApplication, QMainWindow
from PyQt6.QtCore import Qt, QTimer
import cv2
import numpy as np

# Импортируем модули
from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


class TestROIWindowDisplay(unittest.TestCase):
    """Тест для проверки правильного отображения ROI окна"""
    
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
    
    def test_roi_window_independence(self):
        """Тест независимости ROI окна"""
        print("\n=== ТЕСТ НЕЗАВИСИМОСТИ ROI ОКНА ===")
        
        # Проверяем, что окно не имеет родителя
        self.assertIsNone(self.roi_window.parent())
        print("   ✅ ROI окно не имеет родителя")
        
        # Проверяем флаги окна
        window_flags = self.roi_window.windowFlags()
        self.assertTrue(window_flags & Qt.WindowType.Window)
        print("   ✅ ROI окно имеет правильные флаги")
        
        # Проверяем атрибуты окна
        self.assertTrue(self.roi_window.testAttribute(Qt.WidgetAttribute.WA_DeleteOnClose))
        print("   ✅ ROI окно имеет правильные атрибуты")
    
    def test_roi_window_visibility(self):
        """Тест видимости ROI окна"""
        print("\n=== ТЕСТ ВИДИМОСТИ ROI ОКНА ===")
        
        # Проверяем, что окно может быть показано
        self.roi_window.setVisible(True)
        self.assertTrue(self.roi_window.isVisible())
        print("   ✅ ROI окно может быть показано")
        
        # Проверяем, что окно может быть скрыто
        self.roi_window.setVisible(False)
        self.assertFalse(self.roi_window.isVisible())
        print("   ✅ ROI окно может быть скрыто")
        
        # Проверяем, что окно может быть показано снова
        self.roi_window.setVisible(True)
        self.assertTrue(self.roi_window.isVisible())
        print("   ✅ ROI окно может быть показано снова")
    
    def test_roi_window_size_and_position(self):
        """Тест размера и позиции ROI окна"""
        print("\n=== ТЕСТ РАЗМЕРА И ПОЗИЦИИ ROI ОКНА ===")
        
        # Проверяем размер окна
        self.assertEqual(self.roi_window.width(), 1200)
        self.assertEqual(self.roi_window.height(), 800)
        print("   ✅ ROI окно имеет правильный размер")
        
        # Устанавливаем позицию
        self.roi_window.move(100, 100)
        self.assertEqual(self.roi_window.x(), 100)
        self.assertEqual(self.roi_window.y(), 100)
        print("   ✅ ROI окно может быть позиционировано")
    
    def test_roi_window_with_image(self):
        """Тест ROI окна с изображением"""
        print("\n=== ТЕСТ ROI ОКНА С ИЗОБРАЖЕНИЕМ ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        
        # Устанавливаем изображение
        try:
            self.roi_window.set_cv_image(0, test_image)
            print("   ✅ Изображение установлено в ROI окне")
        except Exception as e:
            self.fail(f"Ошибка при установке изображения: {e}")
        
        # Проверяем, что canvas создан
        self.assertIsNotNone(self.roi_window.roi_canvas)
        print("   ✅ Canvas создан в ROI окне")
        
        # Проверяем, что pixmap_item создан
        self.assertIsNotNone(self.roi_window.roi_canvas.pixmap_item)
        print("   ✅ Pixmap item создан в canvas")
    
    def test_roi_window_with_roi(self):
        """Тест ROI окна с ROI"""
        print("\n=== ТЕСТ ROI ОКНА С ROI ===")
        
        # Создаем тестовое изображение
        test_image = np.zeros((480, 640, 3), dtype=np.uint8)
        test_image[:] = (100, 150, 200)
        self.roi_window.set_cv_image(0, test_image)
        
        # Тестовые ROI
        test_rois = [
            [100, 100, 200, 150],
            [300, 200, 150, 100]
        ]
        
        # Устанавливаем ROI
        try:
            self.roi_window.set_rois_from_detector(test_rois)
            print("   ✅ ROI установлены в окне")
        except Exception as e:
            self.fail(f"Ошибка при установке ROI: {e}")
        
        # Проверяем, что ROI добавлены
        self.assertEqual(len(self.roi_window.roi_canvas.rois), 2)
        self.assertEqual(len(self.roi_window.roi_canvas.roi_data), 2)
        print(f"   ✅ ROI добавлены: {len(self.roi_window.roi_canvas.rois)} ROI(s)")
        
        # Проверяем, что список обновлен
        self.assertEqual(self.roi_window.roi_list.count(), 2)
        print(f"   ✅ Список ROI обновлен: {self.roi_window.roi_list.count()} элементов")


if __name__ == '__main__':
    unittest.main()

