#!/usr/bin/env python3
"""
Тестовый скрипт для проверки новой конфигурации с AsyncController.
"""

import asyncio
import sys
import json
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent))

from controller.async_controller import AsyncController


async def test_new_config():
    """Тест новой конфигурации"""
    print("🚀 Тестирование новой конфигурации с AsyncController")
    
    # Создание контроллера
    controller = AsyncController()
    
    # Загрузка новой конфигурации
    config_path = "samples/video_3cam_async.json"
    try:
        with open(config_path, 'r') as f:
            config_data = json.load(f)
        print(f"✅ Новая конфигурация загружена из {config_path}")
    except FileNotFoundError:
        print(f"❌ Файл конфигурации {config_path} не найден")
        return 1
    
    try:
        # Инициализация контроллера с новой конфигурацией
        print("🔄 Инициализация AsyncController с новой конфигурацией...")
        await controller.initialize(config_data)
        print("✅ AsyncController инициализирован")
        
        # Проверка компонентов
        print("\n📋 Проверка компонентов:")
        print(f"  - system config: {controller.config_manager.config_data.get('system', {})}")
        print(f"  - processors: {list(controller.config_manager.config_data.get('processors', {}).keys())}")
        print(f"  - pipelines: {list(controller.config_manager.config_data.get('pipelines', {}).keys())}")
        print(f"  - visualizer: {controller.config_manager.config_data.get('visualizer', {})}")
        print(f"  - controller: {controller.config_manager.config_data.get('controller', {})}")
        
        # Проверка pipeline
        if controller.pipeline:
            print(f"  - pipeline name: {controller.pipeline.config.name}")
            print(f"  - pipeline enabled: {controller.pipeline.config.enabled}")
            print(f"  - pipeline max_concurrent_tasks: {controller.pipeline.config.max_concurrent_tasks}")
        
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
    print("=" * 70)
    print("Тест новой конфигурации с AsyncController")
    print("=" * 70)
    
    try:
        ret = asyncio.run(test_new_config())
        print(f"\n🎯 Тест завершен с кодом: {ret}")
        return ret
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
