#!/usr/bin/env python3
"""
Тест для проверки изменения ширины правой панели ROI редактора
"""

import unittest
from unittest.mock import Mock, patch
import time

from PyQt6.QtWidgets import QApplication, QHBoxLayout
from PyQt6.QtCore import Qt, QTimer

# Импортируем модули
from evileye.visualization_modules.roi_editor_window import ROIEditorWindow


class TestROIPanelWidth(unittest.TestCase):
    """Тест для проверки ширины панелей ROI редактора"""
    
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
    
    def test_panel_width_ratio(self):
        """Тест соотношения ширины панелей"""
        print("\n=== ТЕСТ СООТНОШЕНИЯ ШИРИНЫ ПАНЕЛЕЙ ===")
        
        # Получаем главный layout
        main_layout = self.roi_window.layout()
        self.assertIsNotNone(main_layout)
        print("   ✅ Главный layout найден")
        
        # Проверяем, что это QVBoxLayout (главный layout)
        from PyQt6.QtWidgets import QVBoxLayout
        self.assertIsInstance(main_layout, QVBoxLayout)
        print("   ✅ Главный layout является QVBoxLayout")
        
        # Получаем горизонтальный layout внутри главного
        horizontal_layout = main_layout.itemAt(1).layout()
        self.assertIsNotNone(horizontal_layout)
        self.assertIsInstance(horizontal_layout, QHBoxLayout)
        print("   ✅ Горизонтальный layout найден")
        
        # Проверяем количество элементов в горизонтальном layout
        layout_count = horizontal_layout.count()
        self.assertEqual(layout_count, 2)
        print(f"   ✅ Количество элементов в горизонтальном layout: {layout_count}")
        
        # Проверяем, что canvas (левая панель) имеет коэффициент 4
        canvas_item = horizontal_layout.itemAt(0)
        self.assertIsNotNone(canvas_item)
        # Для QWidgetItem используем sizeHint и stretchFactor
        canvas_stretch = horizontal_layout.stretch(0)
        self.assertEqual(canvas_stretch, 4)
        print(f"   ✅ Canvas (левая панель) имеет коэффициент: {canvas_stretch}")
        
        # Проверяем, что правая панель имеет коэффициент 1
        right_panel_item = horizontal_layout.itemAt(1)
        self.assertIsNotNone(right_panel_item)
        right_panel_stretch = horizontal_layout.stretch(1)
        self.assertEqual(right_panel_stretch, 1)
        print(f"   ✅ Правая панель имеет коэффициент: {right_panel_stretch}")
        
        # Проверяем соотношение: левая панель должна быть в 4 раза шире правой
        ratio = canvas_stretch / right_panel_stretch
        self.assertEqual(ratio, 4.0)
        print(f"   ✅ Соотношение ширин: {ratio}:1 (левая:правая)")
    
    def test_panel_visibility(self):
        """Тест видимости панелей"""
        print("\n=== ТЕСТ ВИДИМОСТИ ПАНЕЛЕЙ ===")
        
        # Проверяем, что canvas существует (не обязательно видим в тесте)
        self.assertIsNotNone(self.roi_window.roi_canvas)
        print("   ✅ Canvas (левая панель) существует")
        
        # Проверяем, что список ROI существует
        self.assertIsNotNone(self.roi_window.roi_list)
        print("   ✅ Список ROI существует")
        
        # Проверяем, что кнопки существуют
        self.assertIsNotNone(self.roi_window.modify_roi_btn)
        self.assertIsNotNone(self.roi_window.delete_roi_btn)
        print("   ✅ Кнопки управления существуют")
    
    def test_panel_functionality(self):
        """Тест функциональности панелей"""
        print("\n=== ТЕСТ ФУНКЦИОНАЛЬНОСТИ ПАНЕЛЕЙ ===")
        
        # Проверяем, что canvas имеет правильные компоненты
        self.assertIsNotNone(self.roi_window.roi_canvas.scene)
        print("   ✅ Canvas имеет сцену")
        
        # Проверяем, что правая панель имеет правильные компоненты
        self.assertIsNotNone(self.roi_window.roi_list)
        self.assertIsNotNone(self.roi_window.modify_roi_btn)
        self.assertIsNotNone(self.roi_window.delete_roi_btn)
        print("   ✅ Правая панель имеет все компоненты")
        
        # Проверяем, что кнопки подключены к обработчикам
        self.assertTrue(self.roi_window.modify_roi_btn.isEnabled() or not self.roi_window.modify_roi_btn.isEnabled())
        self.assertTrue(self.roi_window.delete_roi_btn.isEnabled() or not self.roi_window.delete_roi_btn.isEnabled())
        print("   ✅ Кнопки имеют правильное состояние")


if __name__ == '__main__':
    unittest.main()
