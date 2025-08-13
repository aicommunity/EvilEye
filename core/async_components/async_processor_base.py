import asyncio
from abc import ABC, abstractmethod
from typing import Generic, TypeVar, Any, Optional, Dict
from collections import deque
import time
from datetime import datetime

from core import EvilEyeBase
from .data_types import Frame, DetectionResult, TrackingResult

T = TypeVar('T')
R = TypeVar('R')


class AsyncProcessorBase(EvilEyeBase, Generic[T, R]):
    """
    Базовый класс для асинхронных процессоров.
    Обеспечивает единообразный интерфейс для всех компонентов pipeline.
    """
    
    def __init__(self, max_queue_size: int = 10, timeout: float = 0.1):
        super().__init__()
        self.input_queue = asyncio.Queue(maxsize=max_queue_size)
        self.output_queue = asyncio.Queue()
        self.running = False
        self.timeout = timeout
        self.processed_count = 0
        self.error_count = 0
        self.last_process_time = 0.0
        self.performance_metrics = {
            'avg_process_time': 0.0,
            'max_process_time': 0.0,
            'min_process_time': float('inf'),
            'total_processed': 0
        }
        
        # Буфер для батчевой обработки
        self.batch_buffer = deque(maxlen=5)
        self.batch_size = 1
        
    async def start(self):
        """Запуск процессора"""
        self.running = True
        asyncio.create_task(self._process_loop())
        print(f"{self.__class__.__name__} started")
    
    async def stop(self):
        """Остановка процессора"""
        self.running = False
        # Очистка очередей
        while not self.input_queue.empty():
            try:
                self.input_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
        print(f"{self.__class__.__name__} stopped")
    
    async def put(self, data: T) -> bool:
        """Добавление данных в очередь обработки"""
        try:
            if self.validate_input(data):
                await self.input_queue.put(data)
                return True
            else:
                print(f"Invalid input data for {self.__class__.__name__}")
                return False
        except asyncio.QueueFull:
            print(f"Input queue full for {self.__class__.__name__}")
            return False
    
    async def get(self) -> Optional[R]:
        """Получение результата обработки"""
        try:
            return await asyncio.wait_for(self.output_queue.get(), timeout=0.1)
        except asyncio.TimeoutError:
            return None
    
    async def _process_loop(self):
        """Основной цикл обработки"""
        while self.running:
            try:
                # Получение данных с таймаутом
                data = await asyncio.wait_for(
                    self.input_queue.get(), timeout=self.timeout
                )
                
                start_time = time.time()
                
                # Обработка данных
                result = await self.process_data(data)
                
                # Валидация результата
                if result and self.validate_output(result):
                    await self.output_queue.put(result)
                    self.processed_count += 1
                    
                    # Обновление метрик производительности
                    process_time = time.time() - start_time
                    self._update_metrics(process_time)
                    self.last_process_time = process_time
                else:
                    self.error_count += 1
                    
            except asyncio.TimeoutError:
                # Таймаут - нормальная ситуация, продолжаем
                continue
            except Exception as e:
                print(f"Error in {self.__class__.__name__}: {str(e)}")
                self.error_count += 1
                await asyncio.sleep(0.01)  # Небольшая пауза при ошибке
    
    async def process_batch(self, batch: list[T]) -> list[R]:
        """Батчевая обработка данных"""
        results = []
        for data in batch:
            if self.validate_input(data):
                result = await self.process_data(data)
                if result and self.validate_output(result):
                    results.append(result)
        return results
    
    def _update_metrics(self, process_time: float):
        """Обновление метрик производительности"""
        metrics = self.performance_metrics
        metrics['total_processed'] += 1
        metrics['max_process_time'] = max(metrics['max_process_time'], process_time)
        metrics['min_process_time'] = min(metrics['min_process_time'], process_time)
        
        # Скользящее среднее
        alpha = 0.1
        metrics['avg_process_time'] = (
            alpha * process_time + 
            (1 - alpha) * metrics['avg_process_time']
        )
    
    def get_metrics(self) -> Dict[str, Any]:
        """Получение метрик производительности"""
        return {
            'processed_count': self.processed_count,
            'error_count': self.error_count,
            'last_process_time': self.last_process_time,
            'queue_size': self.input_queue.qsize(),
            'output_queue_size': self.output_queue.qsize(),
            **self.performance_metrics
        }
    
    @abstractmethod
    async def process_data(self, data: T) -> R:
        """Основной метод обработки данных - должен быть реализован в наследниках"""
        pass
    
    def validate_input(self, data: T) -> bool:
        """Валидация входных данных - может быть переопределен в наследниках"""
        return data is not None
    
    def validate_output(self, result: R) -> bool:
        """Валидация выходных данных - может быть переопределен в наследниках"""
        return result is not None
    
    def set_batch_size(self, batch_size: int):
        """Установка размера батча для батчевой обработки"""
        self.batch_size = max(1, batch_size)
    
    async def flush(self):
        """Обработка оставшихся данных в буфере"""
        if self.batch_buffer:
            batch = list(self.batch_buffer)
            self.batch_buffer.clear()
            results = await self.process_batch(batch)
            for result in results:
                await self.output_queue.put(result)

    # --- Реализация абстрактных методов EvilEyeBase ---
    def default(self):
        pass

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return {}
