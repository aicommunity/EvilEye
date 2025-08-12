import asyncio
from abc import abstractmethod
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
import time
from datetime import datetime

from core import EvilEyeBase
from .async_processor_base import AsyncProcessorBase
from .data_types import Frame, DetectionResult, TrackingResult
from .config_manager import PipelineConfig


class AsyncPipeline(EvilEyeBase):
    """
    Базовый класс для асинхронных pipeline.
    Обеспечивает параллельную обработку данных через цепочку процессоров.
    """
    
    def __init__(self, config: Optional[PipelineConfig] = None):
        super().__init__()
        self.config = config or PipelineConfig(name="default")
        self.processors: Dict[str, AsyncProcessorBase] = {}
        self.running = False
        self.frame_buffer = deque(maxlen=self.config.buffer_size)
        self.performance_metrics = {
            'total_frames_processed': 0,
            'avg_processing_time': 0.0,
            'max_processing_time': 0.0,
            'min_processing_time': float('inf'),
            'errors_count': 0
        }
        self.semaphore = asyncio.Semaphore(self.config.max_concurrent_tasks)
    
    async def start(self):
        """Запуск pipeline"""
        if self.running:
            return
        
        self.running = True
        
        # Запуск всех процессоров
        start_tasks = []
        for processor in self.processors.values():
            if hasattr(processor, 'start') and callable(processor.start):
                start_tasks.append(processor.start())
        
        if start_tasks:
            await asyncio.gather(*start_tasks)
        
        print(f"Pipeline {self.config.name} started")
    
    async def stop(self):
        """Остановка pipeline"""
        if not self.running:
            return
        
        self.running = False
        
        # Остановка всех процессоров
        stop_tasks = []
        for processor in self.processors.values():
            if hasattr(processor, 'stop') and callable(processor.stop):
                stop_tasks.append(processor.stop())
        
        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        print(f"Pipeline {self.config.name} stopped")
    
    def add_processor(self, name: str, processor: AsyncProcessorBase):
        """Добавление процессора в pipeline"""
        self.processors[name] = processor
        print(f"Added processor {name} to pipeline {self.config.name}")
    
    def remove_processor(self, name: str):
        """Удаление процессора из pipeline"""
        if name in self.processors:
            del self.processors[name]
            print(f"Removed processor {name} from pipeline {self.config.name}")
    
    def get_processor(self, name: str) -> Optional[AsyncProcessorBase]:
        """Получение процессора по имени"""
        return self.processors.get(name)
    
    async def process_frame(self, frame: Frame) -> Optional[TrackingResult]:
        """
        Обработка одного кадра через весь pipeline
        
        Args:
            frame: Входной кадр
            
        Returns:
            Результат трекинга или None при ошибке
        """
        if not self.running:
            return None
        
        start_time = time.time()
        
        try:
            async with self.semaphore:
                result = await self._process_frame_through_pipeline(frame)
                
                # Обновление метрик
                process_time = time.time() - start_time
                self._update_metrics(process_time)
                
                return result
                
        except Exception as e:
            print(f"Error processing frame in pipeline {self.config.name}: {e}")
            self.performance_metrics['errors_count'] += 1
            return None
    
    async def process_batch(self, frames: List[Frame]) -> List[TrackingResult]:
        """
        Батчевая обработка кадров
        
        Args:
            frames: Список кадров для обработки
            
        Returns:
            Список результатов трекинга
        """
        if not self.running:
            return []
        
        # Создание задач для параллельной обработки
        tasks = []
        for frame in frames:
            task = asyncio.create_task(self.process_frame(frame))
            tasks.append(task)
        
        # Ожидание завершения всех задач
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Фильтрация результатов
        valid_results = []
        for result in results:
            if isinstance(result, Exception):
                print(f"Error in batch processing: {result}")
                self.performance_metrics['errors_count'] += 1
            elif result is not None:
                valid_results.append(result)
        
        return valid_results
    
    async def _process_frame_through_pipeline(self, frame: Frame) -> Optional[TrackingResult]:
        """
        Внутренний метод для обработки кадра через цепочку процессоров
        Должен быть реализован в наследниках
        """
        raise NotImplementedError("Subclasses must implement _process_frame_through_pipeline")
    
    def _update_metrics(self, process_time: float):
        """Обновление метрик производительности"""
        metrics = self.performance_metrics
        metrics['total_frames_processed'] += 1
        metrics['max_processing_time'] = max(metrics['max_processing_time'], process_time)
        metrics['min_processing_time'] = min(metrics['min_processing_time'], process_time)
        
        # Скользящее среднее
        alpha = 0.1
        metrics['avg_processing_time'] = (
            alpha * process_time + 
            (1 - alpha) * metrics['avg_processing_time']
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        return {
            'pipeline_name': self.config.name,
            'running': self.running,
            'processors_count': len(self.processors),
            'buffer_size': len(self.frame_buffer),
            'max_concurrent_tasks': self.config.max_concurrent_tasks,
            **self.performance_metrics
        }
    
    def get_processor_metrics(self) -> Dict[str, Dict[str, Any]]:
        """Получение метрик всех процессоров"""
        metrics = {}
        for name, processor in self.processors.items():
            if hasattr(processor, 'get_metrics'):
                metrics[name] = processor.get_metrics()
        return metrics
    
    async def flush_buffer(self):
        """Обработка всех кадров в буфере"""
        if not self.frame_buffer:
            return
        
        frames = list(self.frame_buffer)
        self.frame_buffer.clear()
        
        results = await self.process_batch(frames)
        return results
    
    def set_config(self, config: PipelineConfig):
        """Обновление конфигурации pipeline"""
        self.config = config
        self.frame_buffer = deque(maxlen=config.buffer_size)
        self.semaphore = asyncio.Semaphore(config.max_concurrent_tasks)
    
    def validate_pipeline(self) -> List[str]:
        """Валидация pipeline"""
        errors = []
        
        if not self.config.name:
            errors.append("Pipeline name is required")
        
        if self.config.max_concurrent_tasks <= 0:
            errors.append("max_concurrent_tasks must be positive")
        
        if self.config.buffer_size <= 0:
            errors.append("buffer_size must be positive")
        
        # Проверка процессоров
        for processor_name, processor in self.processors.items():
            if not hasattr(processor, 'process_data'):
                errors.append(f"Processor {processor_name} must implement process_data method")
        
        return errors
    
    async def health_check(self) -> Dict[str, Any]:
        """Проверка состояния pipeline"""
        health = {
            'pipeline_name': self.config.name,
            'running': self.running,
            'processors_health': {},
            'overall_health': 'healthy'
        }
        
        # Проверка процессоров
        for name, processor in self.processors.items():
            processor_health = {
                'running': getattr(processor, 'running', False),
                'queue_size': getattr(processor, 'input_queue', None).qsize() if hasattr(processor, 'input_queue') else 0
            }
            
            if hasattr(processor, 'get_metrics'):
                processor_health['metrics'] = processor.get_metrics()
            
            health['processors_health'][name] = processor_health
            
            # Определение общего состояния
            if not processor_health['running']:
                health['overall_health'] = 'unhealthy'
        
        return health
