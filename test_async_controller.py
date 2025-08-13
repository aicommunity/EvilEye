#!/usr/bin/env python3
"""
Тестовый скрипт для проверки AsyncController с полной инициализацией.
"""

import asyncio
import sys
import json
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

from controller.async_controller import AsyncController


async def test_async_controller():
    """Тест AsyncController с полной инициализацией"""
    print("🚀 Тестирование AsyncController с полной инициализацией")
    
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
        
        # Проверка компонентов
        print("\n📋 Проверка компонентов:")
        print(f"  - database_config: {hasattr(controller, 'database_config')}")
        print(f"  - db_controller: {controller.db_controller is not None}")
        print(f"  - obj_handler: {controller.obj_handler is not None}")
        print(f"  - pipeline: {controller.pipeline is not None}")
        print(f"  - show_main_gui: {controller.show_main_gui}")
        print(f"  - show_journal: {controller.show_journal}")
        print(f"  - enable_close_from_gui: {controller.enable_close_from_gui}")
        
        # Проверка параметров базы данных
        if controller.database_config and 'database' in controller.database_config:
            db_config = controller.database_config['database']
            print(f"  - db user_name: {db_config.get('user_name', 'NOT SET')}")
            print(f"  - db database_name: {db_config.get('database_name', 'NOT SET')}")
        
        # Запуск контроллера
        print("\n🔄 Запуск AsyncController...")
        await controller.start()
        print("✅ AsyncController запущен")
        
        # Получение метрик
        metrics = controller.get_metrics()
        print(f"  - Метрики: {metrics}")
        
        # Остановка контроллера
        print("\n🔄 Остановка AsyncController...")
        await controller.stop()
        print("✅ AsyncController остановлен")
        
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
    print("Тест AsyncController с полной инициализацией")
    print("=" * 60)
    
    try:
        ret = asyncio.run(test_async_controller())
        print(f"\n🎯 Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
