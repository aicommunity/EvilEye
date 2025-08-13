#!/usr/bin/env python3
"""
Тестовый скрипт для проверки работы GUI с AsyncController.
"""

import asyncio
import sys
import json
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

try:
    from PyQt6.QtWidgets import QApplication
    pyqt_version = 6
except ImportError:
    from PyQt5.QtWidgets import QApplication
    pyqt_version = 5

from controller.async_controller import AsyncController
from visualization_modules.main_window import MainWindow


async def test_gui_async():
    """Тест GUI с AsyncController"""
    print("🚀 Тестирование GUI с AsyncController")
    
    # Создание приложения
    app = QApplication(sys.argv)
    
    # Создание контроллера
    controller = AsyncController()
    
    try:
        # Инициализация контроллера
        await controller.initialize()
        print("✅ Контроллер инициализирован")
        
        # Создание главного окна
        params = {
            'sources': [
                {
                    'type': 'video_file',
                    'path': '/home/user/Videos/Test3Cam/1/139932-video_trim.mp4',
                    'enabled': True
                }
            ],
            'detectors': [
                {
                    'type': 'ObjectDetectorYolo',
                    'enabled': True,
                    'params': {
                        'model_path': 'yolo11n.pt',
                        'confidence_threshold': 0.5
                    }
                }
            ],
            'trackers': [
                {
                    'type': 'ObjectTrackingBotsort',
                    'enabled': True
                }
            ]
        }
        
        # Создание MainWindow
        main_window = MainWindow(controller, "test_config.json", params, 1600, 720)
        print("✅ MainWindow создан")
        
        # Проверка атрибутов контроллера
        print(f"✅ database_config: {hasattr(controller, 'database_config')}")
        print(f"✅ show_main_gui: {controller.show_main_gui}")
        print(f"✅ show_journal: {controller.show_journal}")
        print(f"✅ enable_close_from_gui: {controller.enable_close_from_gui}")
        
        # Запуск контроллера
        await controller.start()
        print("✅ Контроллер запущен")
        
        # Показ окна
        main_window.show()
        print("✅ Окно показано")
        
        # Запуск приложения
        print("🔄 Запуск GUI приложения...")
        ret = app.exec()
        
        # Остановка контроллера
        await controller.stop()
        print("✅ Контроллер остановлен")
        
        return ret
        
    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Основная функция"""
    print("=" * 50)
    print("Тест GUI с AsyncController")
    print("=" * 50)
    
    try:
        ret = asyncio.run(test_gui_async())
        print(f"✅ Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
