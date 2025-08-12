import asyncio
from typing import TypeVar, Generic, Type, Dict, Any, Optional
from dataclasses import dataclass
import time
from collections import deque

T = TypeVar('T')


@dataclass
class ModelInfo:
    """Информация о модели в пуле"""
    model: T
    last_used: float
    use_count: int
    creation_time: float
    is_available: bool = True


class ModelPool(Generic[T]):
    """
    Пул моделей для переиспользования дорогих ресурсов.
    Обеспечивает асинхронный доступ к моделям с кэшированием.
    """
    
    def __init__(self, model_class: Type[T], pool_size: int = 4, 
                 max_idle_time: float = 300.0, lazy_init: bool = True):
        """
        Инициализация пула моделей
        
        Args:
            model_class: Класс модели для создания экземпляров
            pool_size: Максимальный размер пула
            max_idle_time: Максимальное время простоя модели в секундах
            lazy_init: Создавать модели по требованию или сразу
        """
        self.model_class = model_class
        self.pool_size = pool_size
        self.max_idle_time = max_idle_time
        self.lazy_init = lazy_init
        
        self.available_models = asyncio.Queue(maxsize=pool_size)
        self.all_models: Dict[int, ModelInfo] = {}
        self.model_counter = 0
        self.running = False
        
        # Статистика
        self.stats = {
            'total_requests': 0,
            'cache_hits': 0,
            'cache_misses': 0,
            'models_created': 0,
            'models_destroyed': 0,
            'avg_wait_time': 0.0
        }
        
        # Инициализация пула
        if not lazy_init:
            asyncio.create_task(self._initialize_pool())
    
    async def start(self):
        """Запуск пула моделей"""
        if self.running:
            return
        
        self.running = True
        
        # Запуск задачи очистки устаревших моделей
        asyncio.create_task(self._cleanup_task())
        
        # Инициализация пула если нужно
        if self.lazy_init:
            await self._initialize_pool()
        
        print(f"ModelPool started with {self.pool_size} slots")
    
    async def stop(self):
        """Остановка пула моделей"""
        if not self.running:
            return
        
        self.running = False
        
        # Очистка всех моделей
        await self._cleanup_all_models()
        print("ModelPool stopped")
    
    async def get_model(self, timeout: float = 10.0) -> T:
        """
        Получение модели из пула
        
        Args:
            timeout: Таймаут ожидания модели в секундах
            
        Returns:
            Модель из пула
            
        Raises:
            asyncio.TimeoutError: Если модель не получена в течение таймаута
        """
        start_time = time.time()
        self.stats['total_requests'] += 1
        
        try:
            # Попытка получить модель из очереди
            model_info = await asyncio.wait_for(
                self.available_models.get(), timeout=timeout
            )
            
            # Обновление статистики
            wait_time = time.time() - start_time
            self._update_avg_wait_time(wait_time)
            self.stats['cache_hits'] += 1
            
            # Обновление информации о модели
            model_info.last_used = time.time()
            model_info.use_count += 1
            model_info.is_available = False
            
            return model_info.model
            
        except asyncio.TimeoutError:
            # Создание новой модели если пул не полный
            if len(self.all_models) < self.pool_size:
                model = await self._create_model()
                self.stats['cache_misses'] += 1
                return model
            else:
                raise asyncio.TimeoutError(f"Model pool exhausted, timeout: {timeout}s")
    
    async def return_model(self, model: T):
        """
        Возврат модели в пул
        
        Args:
            model: Модель для возврата
        """
        # Поиск информации о модели
        model_info = None
        for info in self.all_models.values():
            if info.model == model:
                model_info = info
                break
        
        if model_info is None:
            print("Warning: Attempting to return unknown model to pool")
            return
        
        # Проверка времени простоя
        idle_time = time.time() - model_info.last_used
        if idle_time > self.max_idle_time:
            # Удаление устаревшей модели
            await self._destroy_model(model_info)
        else:
            # Возврат модели в пул
            model_info.is_available = True
            try:
                self.available_models.put_nowait(model_info)
            except asyncio.QueueFull:
                # Пул переполнен, удаляем модель
                await self._destroy_model(model_info)
    
    async def _create_model(self) -> T:
        """Создание новой модели"""
        model_id = self.model_counter
        self.model_counter += 1
        
        # Создание модели (может быть асинхронным)
        if hasattr(self.model_class, 'create_async'):
            model = await self.model_class.create_async()
        else:
            model = self.model_class()
        
        # Создание информации о модели
        model_info = ModelInfo(
            model=model,
            last_used=time.time(),
            use_count=0,
            creation_time=time.time()
        )
        
        self.all_models[model_id] = model_info
        self.stats['models_created'] += 1
        
        print(f"Created model {model_id} in pool")
        return model
    
    async def _destroy_model(self, model_info: ModelInfo):
        """Уничтожение модели"""
        # Очистка ресурсов модели если нужно
        if hasattr(model_info.model, 'cleanup'):
            if asyncio.iscoroutinefunction(model_info.model.cleanup):
                await model_info.model.cleanup()
            else:
                model_info.model.cleanup()
        
        # Удаление из словаря
        model_id = None
        for mid, info in self.all_models.items():
            if info == model_info:
                model_id = mid
                break
        
        if model_id is not None:
            del self.all_models[model_id]
            self.stats['models_destroyed'] += 1
            print(f"Destroyed model {model_id} from pool")
    
    async def _initialize_pool(self):
        """Инициализация пула моделей"""
        init_tasks = []
        for _ in range(self.pool_size):
            task = asyncio.create_task(self._create_and_add_model())
            init_tasks.append(task)
        
        await asyncio.gather(*init_tasks, return_exceptions=True)
        print(f"ModelPool initialized with {len(self.all_models)} models")
    
    async def _create_and_add_model(self):
        """Создание и добавление модели в пул"""
        try:
            model = await self._create_model()
            model_info = self.all_models[self.model_counter - 1]
            
            # Добавление в очередь доступных моделей
            try:
                self.available_models.put_nowait(model_info)
            except asyncio.QueueFull:
                # Пул уже полный, удаляем модель
                await self._destroy_model(model_info)
        except Exception as e:
            print(f"Error creating model for pool: {e}")
    
    async def _cleanup_task(self):
        """Задача очистки устаревших моделей"""
        while self.running:
            try:
                await asyncio.sleep(60)  # Проверка каждую минуту
                await self._cleanup_idle_models()
            except Exception as e:
                print(f"Error in cleanup task: {e}")
    
    async def _cleanup_idle_models(self):
        """Очистка устаревших моделей"""
        current_time = time.time()
        models_to_remove = []
        
        for model_id, model_info in self.all_models.items():
            if model_info.is_available:
                idle_time = current_time - model_info.last_used
                if idle_time > self.max_idle_time:
                    models_to_remove.append(model_info)
        
        # Удаление устаревших моделей
        for model_info in models_to_remove:
            await self._destroy_model(model_info)
        
        if models_to_remove:
            print(f"Cleaned up {len(models_to_remove)} idle models")
    
    async def _cleanup_all_models(self):
        """Очистка всех моделей"""
        cleanup_tasks = []
        for model_info in self.all_models.values():
            task = asyncio.create_task(self._destroy_model(model_info))
            cleanup_tasks.append(task)
        
        if cleanup_tasks:
            await asyncio.gather(*cleanup_tasks, return_exceptions=True)
    
    def _update_avg_wait_time(self, wait_time: float):
        """Обновление среднего времени ожидания"""
        alpha = 0.1
        self.stats['avg_wait_time'] = (
            alpha * wait_time + 
            (1 - alpha) * self.stats['avg_wait_time']
        )
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики пула"""
        return {
            'pool_size': self.pool_size,
            'active_models': len([m for m in self.all_models.values() if not m.is_available]),
            'available_models': self.available_models.qsize(),
            'total_models': len(self.all_models),
            'cache_hit_rate': (
                self.stats['cache_hits'] / max(self.stats['total_requests'], 1)
            ),
            **self.stats
        }
    
    def get_model_info(self) -> Dict[int, Dict[str, Any]]:
        """Получение информации о всех моделях"""
        info = {}
        for model_id, model_info in self.all_models.items():
            info[model_id] = {
                'last_used': model_info.last_used,
                'use_count': model_info.use_count,
                'creation_time': model_info.creation_time,
                'is_available': model_info.is_available,
                'idle_time': time.time() - model_info.last_used
            }
        return info
