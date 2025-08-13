#!/usr/bin/env python3
"""
Асинхронный пример детекции и трекинга с использованием новой архитектуры.
Демонстрирует использование AsyncPipelineSurveillance и ModelPool.
"""

import asyncio
import argparse
import json
import sys
from pathlib import Path

# Добавляем путь к проекту
sys.path.append(str(Path(__file__).parent.parent))

from pipelines.async_pipelines import AsyncPipelineSurveillance
from core.async_components.data_types import Frame, DetectionResult, TrackingResult, BoundingBox, Track
from core.async_components.config_manager import PipelineConfig, ProcessorConfig
import numpy as np
from datetime import datetime


async def create_sample_frame_with_objects(frame_id: int, source_id: int = 1) -> Frame:
    """Создание тестового кадра с объектами"""
    # Создание случайного изображения
    image_data = np.random.randint(0, 255, (480, 640, 3), dtype=np.uint8)
    
    # Добавляем "объекты" - яркие области
    for i in range(3):
        x1, y1 = np.random.randint(50, 590), np.random.randint(50, 430)
        x2, y2 = x1 + np.random.randint(30, 100), y1 + np.random.randint(30, 100)
        image_data[y1:y2, x1:x2] = [255, 255, 255]  # Белые прямоугольники
    
    return Frame(
        id=frame_id,
        source_id=source_id,
        timestamp=datetime.now(),
        data=image_data,
        metadata={'test': True, 'objects_count': 3}
    )


class MockDetectionProcessor:
    """Заглушка процессора детекции для демонстрации"""
    
    def __init__(self):
        self.detection_count = 0
    
    async def process_data(self, frame: Frame) -> DetectionResult:
        """Имитация детекции объектов"""
        self.detection_count += 1
        
        # Создаем фиктивные детекции
        detections = []
        for i in range(3):
            bbox = BoundingBox(
                x1=50 + i * 100,
                y1=50 + i * 50,
                x2=150 + i * 100,
                y2=150 + i * 50,
                confidence=0.8 + i * 0.1,
                class_id=i
            )
            detections.append(bbox)
        
        return DetectionResult(
            frame_id=frame.id,
            source_id=frame.source_id,
            timestamp=frame.timestamp,
            detections=detections,
            metadata={'processor': 'MockDetectionProcessor'}
        )


class MockTrackingProcessor:
    """Заглушка процессора трекинга для демонстрации"""
    
    def __init__(self):
        self.track_id_counter = 0
        self.tracks = {}
    
    async def process_data(self, detection_result: DetectionResult) -> TrackingResult:
        """Имитация трекинга объектов"""
        tracks = []
        
        for detection in detection_result.detections:
            # Создаем или обновляем трек
            if detection.class_id not in self.tracks:
                self.track_id_counter += 1
                self.tracks[detection.class_id] = self.track_id_counter
            
            track = Track(
                track_id=self.tracks[detection.class_id],
                bounding_box=detection,
                confidence=detection.confidence,
                class_id=detection.class_id,
                life_time=1.0,
                frame_count=1
            )
            tracks.append(track)
        
        return TrackingResult(
            frame_id=detection_result.frame_id,
            source_id=detection_result.source_id,
            timestamp=detection_result.timestamp,
            tracks=tracks,
            metadata={'processor': 'MockTrackingProcessor'}
        )


async def async_detection_tracking_demo():
    """Демонстрация асинхронной детекции и трекинга"""
    print("=== Асинхронная детекция и трекинг ===")
    
    # Создание конфигурации pipeline
    config = PipelineConfig(
        name="detection_tracking_demo",
        enabled=True,
        max_concurrent_tasks=4,
        buffer_size=50
    )
    
    # Создание pipeline
    pipeline = AsyncPipelineSurveillance(config)
    
    # Создание процессоров
    detection_processor = MockDetectionProcessor()
    tracking_processor = MockTrackingProcessor()
    
    # Настройка pipeline
    pipeline.setup_processors(
        capture_processor=None,  # Не используем capture в этом примере
        detection_processor=detection_processor,
        tracking_processor=tracking_processor
    )
    
    try:
        # Запуск pipeline
        await pipeline.start()
        print("Pipeline запущен успешно")
        
        # Обработка кадров
        for i in range(10):
            frame = await create_sample_frame_with_objects(i)
            
            # Обработка через pipeline
            result = await pipeline.process_frame(frame)
            
            if result:
                print(f"Кадр {i}: найдено {len(result.tracks)} треков")
                for track in result.tracks:
                    print(f"  Трек {track.track_id}: класс {track.class_id}, уверенность {track.confidence:.2f}")
            else:
                print(f"Кадр {i}: результат пустой")
            
            await asyncio.sleep(0.1)
        
        # Получение метрик
        metrics = pipeline.get_detailed_metrics()
        print(f"Метрики pipeline: {metrics}")
        
        # Проверка здоровья
        health = await pipeline.health_check()
        print(f"Статус здоровья: {health['overall_health']}")
        
        # Рекомендации по производительности
        recommendations = pipeline.get_performance_recommendations()
        if recommendations:
            print("Рекомендации по производительности:")
            for rec in recommendations:
                print(f"  - {rec}")
        
    finally:
        await pipeline.stop()
        print("Pipeline остановлен")


async def async_batch_processing_demo():
    """Демонстрация батчевой обработки детекции и трекинга"""
    print("\n=== Батчевая обработка детекции и трекинга ===")
    
    config = PipelineConfig(
        name="batch_demo",
        enabled=True,
        max_concurrent_tasks=8,
        buffer_size=100
    )
    
    pipeline = AsyncPipelineSurveillance(config)
    
    detection_processor = MockDetectionProcessor()
    tracking_processor = MockTrackingProcessor()
    
    pipeline.setup_processors(
        capture_processor=None,
        detection_processor=detection_processor,
        tracking_processor=tracking_processor
    )
    
    try:
        await pipeline.start()
        
        # Создание батча кадров
        frames = []
        for i in range(20):
            frame = await create_sample_frame_with_objects(i)
            frames.append(frame)
        
        # Батчевая обработка
        start_time = datetime.now()
        results = await pipeline.process_batch_optimized(frames)
        end_time = datetime.now()
        
        processing_time = (end_time - start_time).total_seconds()
        fps = len(frames) / processing_time
        
        print(f"Батчевая обработка: {len(frames)} кадров за {processing_time:.2f}s")
        print(f"Скорость обработки: {fps:.2f} FPS")
        print(f"Результатов: {len(results)}")
        
        # Статистика по трекам
        total_tracks = sum(len(result.tracks) for result in results if result)
        print(f"Всего треков: {total_tracks}")
        
    finally:
        await pipeline.stop()


async def async_model_pool_demo():
    """Демонстрация работы с пулом моделей"""
    print("\n=== Демонстрация пула моделей ===")
    
    from pipelines.async_pipelines.model_pool import ModelPool
    
    # Создание пула моделей
    class MockModel:
        def __init__(self, model_id):
            self.model_id = model_id
            self.usage_count = 0
        
        async def process(self, data):
            self.usage_count += 1
            return f"Processed by model {self.model_id}"
    
    model_pool = ModelPool(MockModel, pool_size=3, max_idle_time=60.0)
    
    try:
        await model_pool.start()
        print("Пул моделей запущен")
        
        # Получение моделей из пула
        models = []
        for i in range(5):
            model = await model_pool.get_model()
            models.append(model)
            print(f"Получена модель {model.model_id}")
        
        # Использование моделей
        for model in models:
            result = await model.process("test_data")
            print(f"Результат: {result}")
        
        # Возврат моделей в пул
        for model in models:
            await model_pool.return_model(model)
            print(f"Модель {model.model_id} возвращена в пул")
        
        # Статистика пула
        stats = model_pool.get_stats()
        print(f"Статистика пула: {stats}")
        
    finally:
        await model_pool.stop()
        print("Пул моделей остановлен")


async def main():
    """Основная функция демонстрации"""
    parser = argparse.ArgumentParser(description='Асинхронный пример детекции и трекинга')
    parser.add_argument('--demo', choices=['detection', 'batch', 'pool', 'all'], 
                       default='all', help='Тип демонстрации')
    
    args = parser.parse_args()
    
    print("🚀 Асинхронный пример детекции и трекинга EvilEye")
    print("=" * 60)
    
    try:
        if args.demo == 'detection' or args.demo == 'all':
            await async_detection_tracking_demo()
        
        if args.demo == 'batch' or args.demo == 'all':
            await async_batch_processing_demo()
        
        if args.demo == 'pool' or args.demo == 'all':
            await async_model_pool_demo()
        
        print("\n✅ Все демонстрации завершены успешно!")
        
    except Exception as e:
        print(f"❌ Ошибка в демонстрации: {e}")
        raise


if __name__ == "__main__":
    asyncio.run(main())
