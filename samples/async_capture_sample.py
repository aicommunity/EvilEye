#!/usr/bin/env python3
"""
Асинхронный пример захвата видео с использованием новой архитектуры.
Демонстрирует использование AsyncController и новых типов данных.
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent))

from controller.async_controller import AsyncController
from core.async_components.data_types import Frame
import numpy as np
from datetime import datetime


async def create_sample_frame(frame_id: int, source_id: int = 1) -> Frame:
    """Создание тестового кадра"""
    # Создание случайного изображения
    image_data = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    return Frame(
        id=frame_id,
        source_id=source_id,
        timestamp=datetime.now(),
        data=image_data,
        metadata={'test': True}
    )


async def async_capture_demo():
    """Демонстрация асинхронного захвата"""
    print("=== Асинхронный захват видео ===")
    
    # Создание контроллера
    controller = AsyncController()
    
    try:
        # Инициализация с конфигурацией по умолчанию
        await controller.initialize()
        
        # Запуск контроллера
        await controller.start()
        
        print("Контроллер запущен успешно")
        
        # Обработка нескольких тестовых кадров
        for i in range(5):
            frame = await create_sample_frame(i)
            result = await controller.process_frame(frame)
            
            if result:
                print(f"Обработан кадр {i}: найдено {len(result.tracks)} треков")
            else:
                print(f"Обработан кадр {i}: результат пустой")
            
            # Небольшая пауза между кадрами
            await asyncio.sleep(0.1)
        
        # Получение метрик
        metrics = controller.get_metrics()
        print(f"Метрики контроллера: {metrics['controller']}")
        
        # Проверка здоровья системы
        health = await controller.get_health_status()
        print(f"Статус здоровья: {health['overall_health']}")
        
    finally:
        # Остановка контроллера
        await controller.stop()
        print("Контроллер остановлен")


async def async_batch_processing_demo():
    """Демонстрация батчевой обработки"""
    print("\n=== Батчевая обработка ===")
    
    controller = AsyncController()
    
    try:
        await controller.initialize()
        await controller.start()
        
        # Создание батча кадров
        frames = []
        for i in range(10):
            frame = await create_sample_frame(i)
            frames.append(frame)
        
        # Батчевая обработка
        results = await controller.process_batch(frames)
        print(f"Батчевая обработка: {len(frames)} кадров -> {len(results)} результатов")
        
        # Детальные метрики pipeline
        if controller.pipeline:
            pipeline_metrics = controller.pipeline.get_detailed_metrics()
            print(f"Метрики pipeline: {pipeline_metrics}")
        
    finally:
        await controller.stop()


async def async_config_demo():
    """Демонстрация работы с конфигурацией"""
    print("\n=== Работа с конфигурацией ===")
    
    # Создание кастомной конфигурации
    custom_config = {
        'system': {
            'fps': 30,
            'max_memory_usage_mb': 8192,
            'debug_mode': True,
            'log_level': 'INFO'
        },
        'processors': {
            'video_capture': {
                'type': 'VideoCapture',
                'enabled': True,
                'max_queue_size': 10,
                'timeout': 0.1,
                'params': {
                    'fps': 30,
                    'resolution': [1280, 720]
                }
            }
        },
        'pipelines': {
            'surveillance': {
                'enabled': True,
                'max_concurrent_tasks': 4,
                'buffer_size': 100
            }
        }
    }
    
    controller = AsyncController()
    
    try:
        # Инициализация с кастомной конфигурацией
        await controller.initialize(custom_config)
        
        # Получение сводки конфигурации
        config_summary = controller.get_config_summary()
        print(f"Сводка конфигурации: {config_summary}")
        
        # Сохранение конфигурации в файл
        config_path = "async_config_demo.json"
        await controller.save_config(config_path)
        print(f"Конфигурация сохранена в {config_path}")
        
        # Загрузка конфигурации из файла
        new_controller = AsyncController()
        await new_controller.load_config(config_path)
        print("Конфигурация загружена из файла")
        
        # Удаление временного файла
        import os
        os.remove(config_path)
        
    finally:
        await controller.stop()


async def main():
    """Основная функция демонстрации"""
    parser = argparse.ArgumentParser(description='Асинхронный пример захвата видео')
    parser.add_argument('--demo', choices=['capture', 'batch', 'config', 'all'], 
                       default='all', help='Тип демонстрации')
    
    args = parser.parse_args()
    
    print("🚀 Асинхронный пример захвата видео EvilEye")
    print("=" * 50)
    
    try:
        if args.demo == 'capture' or args.demo == 'all':
            await async_capture_demo()
        
        if args.demo == 'batch' or args.demo == 'all':
            await async_batch_processing_demo()
        
        if args.demo == 'config' or args.demo == 'all':
            await async_config_demo()
        
        print("\n✅ Все демонстрации завершены успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в демонстрации: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
