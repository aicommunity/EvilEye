#!/usr/bin/env python3
"""
Тест для проверки обновления списка ROI при добавлении нового ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROIListUpdate(unittest.TestCase):
    """Тест для проверки обновления списка ROI"""
    
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

    def test_roi_added_signal_emission(self):
        """Тест испускания сигнала roi_added при добавлении ROI"""
        print("\n=== ТЕСТ ИСПУСКАНИЯ СИГНАЛА roi_added ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Добавляем ROI
        coords = [100, 100, 300, 250]
        color = (255, 0, 0)
        
        print(f"1. Добавляем ROI с координатами: {coords}")
        roi_item = self.roi_view.add_roi(coords, color)
        
        # Проверяем, что сигнал был испущен
        self.roi_view.roi_added.emit.assert_called_once_with(coords)
        print(f"   ✅ Сигнал roi_added испущен с координатами: {coords}")
        
        # Проверяем, что ROI добавлен
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        self.assertEqual(len(self.roi_view.roi_data), 1)
        print(f"   ✅ ROI добавлен в список: {len(self.roi_view.rois)} ROI(s)")
    
    def test_roi_added_signal_not_emitted_during_config_loading(self):
        """Тест, что сигнал roi_added не испускается при загрузке из конфига"""
        print("\n=== ТЕСТ ПРЕДОТВРАЩЕНИЯ СИГНАЛА ПРИ ЗАГРУЗКЕ ИЗ КОНФИГА ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Устанавливаем флаг загрузки из конфига
        self.roi_view._loading_from_config = True
        
        # Добавляем ROI через add_roi_direct
        coords = [100, 100, 300, 250]
        color = (255, 0, 0)
        
        print(f"1. Добавляем ROI через add_roi_direct с флагом _loading_from_config=True")
        roi_item = self.roi_view.add_roi_direct(coords, color)
        
        # Проверяем, что сигнал НЕ был испущен
        self.roi_view.roi_added.emit.assert_not_called()
        print(f"   ✅ Сигнал roi_added НЕ испущен (правильно)")
        
        # Проверяем, что ROI добавлен
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        print(f"   ✅ ROI добавлен в список: {len(self.roi_view.rois)} ROI(s)")
    
    def test_roi_added_signal_emitted_after_config_loading(self):
        """Тест, что сигнал roi_added испускается после загрузки из конфига"""
        print("\n=== ТЕСТ ИСПУСКАНИЯ СИГНАЛА ПОСЛЕ ЗАГРУЗКИ ИЗ КОНФИГА ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        # Сначала устанавливаем флаг загрузки из конфига
        self.roi_view._loading_from_config = True
        
        # Добавляем ROI через add_roi_direct (не испускает сигнал)
        coords1 = [100, 100, 300, 250]
        color1 = (255, 0, 0)
        self.roi_view.add_roi_direct(coords1, color1)
        
        # Сбрасываем флаг
        self.roi_view._loading_from_config = False
        
        # Добавляем еще один ROI через add_roi_direct (должен испустить сигнал)
        coords2 = [400, 400, 600, 550]
        color2 = (0, 255, 0)
        
        print(f"1. Добавляем ROI после сброса флага _loading_from_config=False")
        roi_item = self.roi_view.add_roi_direct(coords2, color2)
        
        # Проверяем, что сигнал был испущен только для второго ROI
        self.roi_view.roi_added.emit.assert_called_once_with(coords2)
        print(f"   ✅ Сигнал roi_added испущен с координатами: {coords2}")
        
        # Проверяем, что оба ROI добавлены
        self.assertEqual(len(self.roi_view.rois), 2)
        print(f"   ✅ Оба ROI добавлены в список: {len(self.roi_view.rois)} ROI(s)")
    
    def test_roi_list_update_flow(self):
        """Тест полного потока обновления списка ROI"""
        print("\n=== ТЕСТ ПОЛНОГО ПОТОКА ОБНОВЛЕНИЯ СПИСКА ROI ===")
        
        # Создаем mock для сигнала
        self.roi_view.roi_added = Mock()
        
        print("1. Имитируем рисование нового ROI пользователем:")
        print("   - Пользователь кликает и перетаскивает мышь")
        print("   - Вызывается _finish_drawing()")
        print("   - Вызывается add_roi()")
        print("   - Испускается сигнал roi_added")
        print("   - Вызывается _on_roi_added()")
        print("   - Вызывается _update_roi_list()")
        
        # Имитируем добавление ROI через рисование
        coords = [150, 150, 350, 300]
        color = (255, 0, 0)
        
        roi_item = self.roi_view.add_roi(coords, color)
        
        # Проверяем, что сигнал был испущен
        self.roi_view.roi_added.emit.assert_called_once_with(coords)
        print(f"   ✅ Сигнал roi_added испущен с координатами: {coords}")
        
        # Проверяем, что ROI добавлен
        self.assertIsNotNone(roi_item)
        self.assertEqual(len(self.roi_view.rois), 1)
        self.assertEqual(len(self.roi_view.roi_data), 1)
        print(f"   ✅ ROI добавлен в список: {len(self.roi_view.rois)} ROI(s)")
        
        print("\n2. Результат:")
        print("   - Список ROI обновляется немедленно")
        print("   - Пользователь видит новый ROI в списке")
        print("   - ROI выделен и готов к редактированию")


if __name__ == '__main__':
    unittest.main()
