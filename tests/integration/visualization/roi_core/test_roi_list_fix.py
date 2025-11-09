#!/usr/bin/env python3
"""
Тест для проверки исправления обновления списка ROI
"""

import unittest
import time
from unittest.mock import Mock, patch

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView
from PyQt6.QtCore import Qt, QTimer, QPointF
from PyQt6.QtGui import QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIListFix(unittest.TestCase):
    """Тест для проверки исправления обновления списка ROI"""
    
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

    def test_add_roi_direct_without_loading_flag(self):
        """Тест add_roi_direct без флага загрузки - должен испустить сигнал"""
        print("\n=== ТЕСТ add_roi_direct БЕЗ ФЛАГА ЗАГРУЗКИ ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Убеждаемся, что флаг не установлен
        if hasattr(self.roi_view, '_loading_from_config'):
            delattr(self.roi_view, '_loading_from_config')
        
        # Добавляем ROI
        coords = [100, 100, 300, 250]
        color = (255, 0, 0)
        
        print(f"1. Добавляем ROI с координатами: {coords}")
        roi_item = self.roi_view.add_roi_direct(coords, color)
        
        # Проверяем, что сигнал был испущен
        self.roi_view.roi_added.emit.assert_called_once_with(coords)
        print(f"   ✅ Сигнал roi_added испущен с координатами: {coords}")
        
        # Проверяем, что ROI добавлен в данные
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        self.assertEqual(len(self.roi_view.roi_data), 1)
        print(f"   ✅ ROI добавлен в данные: {len(self.roi_view.roi_data)} ROI(s)")
    
    def test_add_roi_direct_with_loading_flag(self):
        """Тест add_roi_direct с флагом загрузки - НЕ должен испустить сигнал"""
        print("\n=== ТЕСТ add_roi_direct С ФЛАГОМ ЗАГРУЗКИ ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Устанавливаем флаг загрузки из конфига
        self.roi_view._loading_from_config = True
        
        # Добавляем ROI
        coords = [100, 100, 300, 250]
        color = (255, 0, 0)
        
        print(f"1. Добавляем ROI с флагом _loading_from_config=True")
        roi_item = self.roi_view.add_roi_direct(coords, color)
        
        # Проверяем, что сигнал НЕ был испущен
        self.roi_view.roi_added.emit.assert_not_called()
        print(f"   ✅ Сигнал roi_added НЕ испущен (правильно)")
        
        # Проверяем, что ROI добавлен в rois
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        # add_roi_direct не добавляет в roi_data, если установлен флаг _loading_from_config
        # Проверяем, что ROI добавлен в rois
        print(f"   ✅ ROI добавлен в rois: {len(self.roi_view.rois)} ROI(s)")
    
    def test_add_roi_always_emits_signal(self):
        """Тест add_roi всегда испускает сигнал"""
        print("\n=== ТЕСТ add_roi ВСЕГДА ИСПУСКАЕТ СИГНАЛ ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Добавляем ROI через add_roi
        coords = [200, 200, 400, 350]
        color = (0, 255, 0)
        
        print(f"1. Добавляем ROI через add_roi с координатами: {coords}")
        roi_item = self.roi_view.add_roi(coords, color)
        
        # Проверяем, что сигнал был испущен
        self.roi_view.roi_added.emit.assert_called_once_with(coords)
        print(f"   ✅ Сигнал roi_added испущен с координатами: {coords}")
        
        # Проверяем, что ROI добавлен в данные
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        self.assertEqual(len(self.roi_view.roi_data), 1)
        print(f"   ✅ ROI добавлен в данные: {len(self.roi_view.roi_data)} ROI(s)")
    
    def test_roi_data_synchronization(self):
        """Тест синхронизации roi_data и rois"""
        print("\n=== ТЕСТ СИНХРОНИЗАЦИИ roi_data И rois ===")
        
        # Добавляем несколько ROI
        coords1 = [100, 100, 200, 200]
        coords2 = [300, 300, 400, 400]
        coords3 = [500, 500, 600, 600]
        
        print("1. Добавляем 3 ROI через add_roi_direct")
        # Не устанавливаем флаг _loading_from_config, чтобы roi_data добавлялся
        if hasattr(self.roi_view, '_loading_from_config'):
            delattr(self.roi_view, '_loading_from_config')
        
        self.roi_view.add_roi_direct(coords1, (255, 0, 0))
        self.roi_view.add_roi_direct(coords2, (0, 255, 0))
        self.roi_view.add_roi_direct(coords3, (0, 0, 255))
        
        # Проверяем синхронизацию
        self.assertEqual(len(self.roi_view.rois), 3)
        self.assertEqual(len(self.roi_view.roi_data), 3)
        
        print(f"   ✅ Количество ROI в rois: {len(self.roi_view.rois)}")
        print(f"   ✅ Количество ROI в roi_data: {len(self.roi_view.roi_data)}")
        
        # Проверяем, что данные соответствуют
        for i, roi_data in enumerate(self.roi_view.roi_data):
            expected_coords = [coords1, coords2, coords3][i]
            self.assertEqual(roi_data['coords'], expected_coords)
            print(f"   ✅ ROI_{i+1} данные корректны: {roi_data['coords']}")


if __name__ == '__main__':
    unittest.main()

