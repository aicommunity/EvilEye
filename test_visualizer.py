#!/usr/bin/env python3
"""
Тестовый скрипт для проверки инициализации Visualizer в AsyncController.
"""

import asyncio
import sys
import json
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

from controller.async_controller import AsyncController


async def test_visualizer():
    """Тест инициализации Visualizer"""
    print("🚀 Тестирование инициализации Visualizer")
    
    # Создание контроллера
    controller = AsyncController()
    
    # Загрузка тестовой конфигурации
    config_path = "samples/video_3cam.json"
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        print(f"✅ Конфигурация загружена из {config_path}")
    except FileNotFoundError:
        print(f"❌ Файл конфигурации {config_path} не найден")
        return 1
    
    try:
        # Инициализация контроллера
        print("🔄 Инициализация AsyncController...")
        await controller.initialize(config_data)
        print("✅ AsyncController инициализирован")
        
        # Создание фиктивных slots и signals
        mock_slots = {
            'update_image': lambda *args: None,
            'open_zone_win': lambda *args: None
        }
        mock_signals = {
            'display_zones_signal': type('Signal', (), {'connect': lambda self, func: None})(),
            'add_zone_signal': type('Signal', (), {'connect': lambda self, func: None})()
        }
        
        # Инициализация главного окна (это вызовет инициализацию Visualizer)
        print("🔄 Инициализация MainWindow...")
        controller.init_main_window(None, mock_slots, mock_signals)
        print("✅ MainWindow инициализирован")
        
        # Проверка Visualizer
        print("\n📋 Проверка Visualizer:")
        print(f"  - visualizer: {controller.visualizer is not None}")
        print(f"  - pyqt_slots: {controller.pyqt_slots is not None}")
        print(f"  - pyqt_signals: {controller.pyqt_signals is not None}")
        
        if controller.visualizer:
            print(f"  - visualizer.gui_enabled: {getattr(controller.visualizer, 'gui_enabled', 'N/A')}")
            print(f"  - visualizer.source_id_name_table: {getattr(controller.visualizer, 'source_id_name_table', 'N/A')}")
        
        print("\n✅ Все тесты прошли успешно!")
        return 0
        
    except Exception as e:
        print(f"❌ Ошибка в тесте: {e}")
        import traceback
        traceback.print_exc()
        return 1


def main():
    """Основная функция"""
    print("=" * 60)
    print("Тест инициализации Visualizer в AsyncController")
    print("=" * 60)
    
    try:
        ret = asyncio.run(test_visualizer())
        print(f"\n🎯 Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
