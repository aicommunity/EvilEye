#!/usr/bin/env python3
"""
Тест для проверки логирования информации о выбранном ROI
"""

import unittest
import time
from unittest.mock import Mock, patch, MagicMock

from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QGraphicsRectItem
from PyQt6.QtCore import Qt, QTimer, QRectF, QPointF
from PyQt6.QtGui import QPen, QColor, QPixmap

# Импортируем модули
from evileye.visualization_modules.roi_core import ROIGraphicsView


class TestROILogging(unittest.TestCase):
    """Тест для проверки логирования информации о выбранном ROI"""
    
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

    def test_log_selected_roi_info(self):
        """Тест логирования информации о выбранном ROI"""
        print("\n=== ТЕСТ ЛОГИРОВАНИЯ ИНФОРМАЦИИ О ВЫБРАННОМ ROI ===")
        
        # Создаем mock ROI
        roi_item = Mock(spec=QGraphicsRectItem)
        pen = Mock()
        pen.color.return_value = QColor(255, 100, 100)  # Цвет выделения
        pen.width.return_value = 8  # Толщина выделения
        roi_item.pen.return_value = pen
        
        # Добавляем ROI в списки
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (0, 255, 0)}]
        
        print("1. Вызываем _log_selected_roi_info для ROI с ID=0...")
        self.roi_view._log_selected_roi_info(0)
        
        # Проверяем, что логгер был вызван
        self.roi_view.logger.info.assert_called()
        
        # Получаем последний вызов логгера
        last_call = self.roi_view.logger.info.call_args[0][0]
        print(f"   ✅ Лог записан: {last_call}")
        
        # Проверяем содержимое лога
        self.assertIn("Selected ROI info:", last_call)
        self.assertIn("ID=0", last_call)
        self.assertIn("pen_color=RGB(255,100,100)", last_call)
        self.assertIn("pen_width=8", last_call)
        self.assertIn("original_color=(0, 255, 0)", last_call)
        
        print("   ✅ Лог содержит всю необходимую информацию:")
        print("      - ID выбранного ROI")
        print("      - Цвет пера (RGB)")
        print("      - Толщина пера")
        print("      - Оригинальный цвет")
    
    def test_set_roi_state_logging(self):
        """Тест логирования при обновлении состояния ROI"""
        print("\n=== ТЕСТ ЛОГИРОВАНИЯ ПРИ ОБНОВЛЕНИИ СОСТОЯНИЯ ROI ===")
        
        # Создаем mock ROI
        roi_item = Mock(spec=QGraphicsRectItem)
        pen = Mock()
        pen.color.return_value = QColor(255, 100, 100)
        pen.width.return_value = 8
        roi_item.pen.return_value = pen
        
        # Добавляем ROI в списки
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (255, 0, 0)}]
        
        print("1. Вызываем set_roi_state с selected_id=0...")
        self.roi_view.set_roi_state(selected_id=0)
        
        # Проверяем, что логгер был вызван дважды
        # 1. Для "ROI state updated: selected_id = 0"
        # 2. Для "Selected ROI info: ..."
        self.assertEqual(self.roi_view.logger.info.call_count, 2)
        
        # Получаем оба вызова логгера
        calls = [call[0][0] for call in self.roi_view.logger.info.call_args_list]
        
        print(f"   ✅ Логи записаны:")
        for i, call in enumerate(calls, 1):
            print(f"      {i}. {call}")
        
        # Проверяем содержимое логов
        self.assertIn("ROI state updated: selected_id = 0", calls[0])
        self.assertIn("Selected ROI info:", calls[1])
        self.assertIn("ID=0", calls[1])
        self.assertIn("pen_color=RGB(255,100,100)", calls[1])
        self.assertIn("pen_width=8", calls[1])
        self.assertIn("original_color=(255, 0, 0)", calls[1])
    
    def test_mouse_release_logging(self):
        """Тест логирования при отпускании мыши"""
        print("\n=== ТЕСТ ЛОГИРОВАНИЯ ПРИ ОТПУСКАНИИ МЫШИ ===")
        
        # Создаем mock ROI
        roi_item = Mock(spec=QGraphicsRectItem)
        pen = Mock()
        pen.color.return_value = QColor(255, 100, 100)
        pen.width.return_value = 8
        roi_item.pen.return_value = pen
        
        # Добавляем ROI в списки
        self.roi_view.rois = [roi_item]
        self.roi_view.roi_data = [{"coords": [100, 100, 300, 250], "color": (0, 0, 255)}]
        
        # Устанавливаем выбранный ROI
        self.roi_view.selected_roi_id = 0
        self.roi_view.roi_state['selected_id'] = 0
        
        # Создаем mock событие мыши
        mock_event = Mock()
        mock_event.button.return_value = Qt.MouseButton.LeftButton
        mock_event.pos.return_value = QPointF(100, 100)
        
        # Mock для mapToScene
        self.roi_view.mapToScene = Mock(return_value=QPointF(200, 200))
        
        print("1. Имитируем отпускание мыши...")
        self.roi_view.mouseReleaseEvent(mock_event)
        
        # Проверяем, что логгер был вызван дважды
        # 1. Для "Mouse released at scene position: ..."
        # 2. Для "Selected ROI info: ..."
        self.assertEqual(self.roi_view.logger.info.call_count, 2)
        
        # Получаем оба вызова логгера
        calls = [call[0][0] for call in self.roi_view.logger.info.call_args_list]
        
        print(f"   ✅ Логи записаны:")
        for i, call in enumerate(calls, 1):
            print(f"      {i}. {call}")
        
        # Проверяем содержимое логов
        self.assertIn("Mouse released at scene position:", calls[0])
        self.assertIn("Selected ROI info:", calls[1])
        self.assertIn("ID=0", calls[1])
        self.assertIn("pen_color=RGB(255,100,100)", calls[1])
        self.assertIn("pen_width=8", calls[1])
        self.assertIn("original_color=(0, 0, 255)", calls[1])
    
    def test_logging_format_explanation(self):
        """Объяснение формата логирования"""
        print("\n=== ОБЪЯСНЕНИЕ ФОРМАТА ЛОГИРОВАНИЯ ===")
        
        print("1. Формат лога 'ROI state updated':")
        print("   ROI state updated: selected_id = 2")
        print("   - Показывает, что выбран ROI с ID=2")
        
        print("\n2. Формат лога 'Mouse released at scene position':")
        print("   Mouse released at scene position: PyQt6.QtCore.QPointF(2252.199413489736, 1593.431085043988)")
        print("   - Показывает позицию мыши в координатах сцены")
        
        print("\n3. Новый формат лога 'Selected ROI info':")
        print("   Selected ROI info: ID=2, pen_color=RGB(255,100,100), pen_width=8, original_color=(255, 0, 0)")
        print("   - ID: идентификатор выбранного ROI")
        print("   - pen_color: цвет пера (RGB) - ярко-красный для выделения")
        print("   - pen_width: толщина пера в пикселях")
        print("   - original_color: оригинальный цвет ROI")
        
        print("\n4. Примеры цветов:")
        print("   - pen_color=RGB(255,100,100) - ярко-красный (выделение)")
        print("   - original_color=(255, 0, 0) - красный")
        print("   - original_color=(0, 255, 0) - зеленый")
        print("   - original_color=(0, 0, 255) - синий")
        
        print("\n5. Примеры толщины пера:")
        print("   - pen_width=4 - обычная толщина")
        print("   - pen_width=8 - толщина выделения (4 * 2.0 множитель)")


if __name__ == '__main__':
    unittest.main()
