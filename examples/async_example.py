#!/usr/bin/env python3
"""
Пример использования асинхронного контроллера EvilEye.
Демонстрирует возможности новой архитектуры.
"""

import asyncio
import json
from datetime import datetime
from pathlib import Path

from controller.async_controller import AsyncController
from core.async_components.data_types import Frame
import numpy as np


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


async def demo_basic_usage():
    """Демонстрация базового использования"""
    print("=== Демонстрация базового использования ===")
    
    # Создание контроллера
    controller = AsyncController()
    
    try:
        # Инициализация
        await controller.initialize()
        
        # Запуск
        await controller.start()
        
        # Обработка нескольких кадров
        for i in range(5):
            frame = await create_sample_frame(i)
            result = await controller.process_frame(frame)
            
            if result:
                print(f"Обработан кадр {i}: найдено {len(result.tracks)} треков")
            else:
                print(f"Обработан кадр {i}: результат пустой")
        
        # Получение метрик
        metrics = controller.get_metrics()
        print(f"Метрики контроллера: {json.dumps(metrics['controller'], indent=2)}")
        
        # Проверка здоровья системы
        health = await controller.get_health_status()
        print(f"Статус здоровья: {health['overall_health']}")
        
    finally:
        # Остановка
        await controller.stop()


async def demo_batch_processing():
    """Демонстрация батчевой обработки"""
    print("\n=== Демонстрация батчевой обработки ===")
    
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
            print(f"Метрики pipeline: {json.dumps(pipeline_metrics, indent=2)}")
        
    finally:
        await controller.stop()


async def demo_event_handling():
    """Демонстрация обработки событий"""
    print("\n=== Демонстрация обработки событий ===")
    
    controller = AsyncController()
    
    # Счетчик событий
    event_count = {'frame_processed': 0, 'error': 0, 'metrics': 0}
    
    # Обработчик событий
    async def event_counter(event):
        event_type = event.type
        if event_type in event_count:
            event_count[event_type] += 1
            print(f"Событие {event_type}: {event.data}")
    
    try:
        await controller.initialize()
        
        # Подписка на события
        controller.event_bus.subscribe('frame_processed', event_counter)
        controller.event_bus.subscribe('error', event_counter)
        controller.event_bus.subscribe('metrics', event_counter)
        
        await controller.start()
        
        # Обработка кадров для генерации событий
        for i in range(3):
            frame = await create_sample_frame(i)
            await controller.process_frame(frame)
            await asyncio.sleep(0.1)  # Небольшая пауза
        
        # Ожидание обработки событий
        await asyncio.sleep(1)
        
        print(f"Статистика событий: {event_count}")
        
    finally:
        await controller.stop()


async def demo_configuration_management():
    """Демонстрация управления конфигурацией"""
    print("\n=== Демонстрация управления конфигурацией ===")
    
    # Создание кастомной конфигурации
    custom_config = {
        'system': {
            'fps': 60,
            'max_memory_usage_mb': 8192,
            'debug_mode': True,
            'log_level': 'DEBUG'
        },
        'processors': {
            'video_capture': {
                'type': 'VideoCapture',
                'enabled': True,
                'max_queue_size': 20,
                'timeout': 0.05,
                'params': {
                    'fps': 60,
                    'resolution': [1280, 720]
                }
            },
            'object_detector': {
                'type': 'ObjectDetectorYolo',
                'enabled': True,
                'max_queue_size': 15,
                'batch_size': 4,
                'params': {
                    'model': 'yolo11n.pt',
                    'confidence': 0.3,
                    'device': 'cuda'
                }
            }
        },
        'pipelines': {
            'surveillance': {
                'enabled': True,
                'max_concurrent_tasks': 8,
                'buffer_size': 200
            }
        }
    }
    
    controller = AsyncController()
    
    try:
        # Инициализация с кастомной конфигурацией
        await controller.initialize(custom_config)
        
        # Получение сводки конфигурации
        config_summary = controller.get_config_summary()
        print(f"Сводка конфигурации: {json.dumps(config_summary, indent=2)}")
        
        # Сохранение конфигурации в файл
        config_path = "custom_config.json"
        await controller.save_config(config_path)
        print(f"Конфигурация сохранена в {config_path}")
        
        # Загрузка конфигурации из файла
        new_controller = AsyncController()
        await new_controller.load_config(config_path)
        print("Конфигурация загружена из файла")
        
        # Удаление временного файла
        Path(config_path).unlink(missing_ok=True)
        
    finally:
        await controller.stop()


async def demo_performance_monitoring():
    """Демонстрация мониторинга производительности"""
    print("\n=== Демонстрация мониторинга производительности ===")
    
    controller = AsyncController()
    
    try:
        await controller.initialize()
        await controller.start()
        
        # Имитация нагрузки
        start_time = datetime.now()
        
        for i in range(20):
            frame = await create_sample_frame(i)
            await controller.process_frame(frame)
            
            # Периодический вывод метрик
            if i % 5 == 0:
                metrics = controller.get_metrics()
                pipeline_metrics = metrics.get('pipeline', {})
                if pipeline_metrics:
                    avg_time = pipeline_metrics.get('avg_processing_time', 0)
                    total_processed = pipeline_metrics.get('total_frames_processed', 0)
                    print(f"Кадр {i}: среднее время обработки = {avg_time:.3f}s, всего обработано = {total_processed}")
        
        end_time = datetime.now()
        total_time = (end_time - start_time).total_seconds()
        
        print(f"Общее время обработки: {total_time:.2f} секунд")
        print(f"Средняя скорость: {20/total_time:.2f} кадров/сек")
        
        # Получение рекомендаций по производительности
        if controller.pipeline:
            recommendations = controller.pipeline.get_performance_recommendations()
            if recommendations:
                print("Рекомендации по производительности:")
                for rec in recommendations:
                    print(f"  - {rec}")
        
    finally:
        await controller.stop()


async def main():
    """Основная функция демонстрации"""
    print("🚀 Демонстрация асинхронного контроллера EvilEye")
    print("=" * 60)
    
    try:
        # Запуск всех демонстраций
        await demo_basic_usage()
        await demo_batch_processing()
        await demo_event_handling()
        await demo_configuration_management()
        await demo_performance_monitoring()
        
        print("\n✅ Все демонстрации завершены успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в демонстрации: {e}")
        raise


if __name__ == "__main__":
    # Запуск демонстрации
    asyncio.run(main())
