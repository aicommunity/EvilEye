import asyncio
from typing import Dict, List, Any, Callable, Awaitable
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
import weakref


@dataclass
class Event:
    """Класс для представления события"""
    type: str
    data: Any
    timestamp: datetime
    source: str
    metadata: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class EventBus:
    """
    Event Bus для асинхронной обработки событий.
    Позволяет компонентам подписываться на события и получать уведомления.
    """
    
    def __init__(self):
        self.subscribers: Dict[str, List[Callable[[Event], Awaitable[None]]]] = defaultdict(list)
        self.event_history: List[Event] = []
        self.max_history_size = 1000
        self.running = False
        self.event_queue = asyncio.Queue(maxsize=1000)
        self.processing_task = None
        
    async def start(self):
        """Запуск обработки событий"""
        self.running = True
        self.processing_task = asyncio.create_task(self._process_events())
        print("EventBus started")
    
    async def stop(self):
        """Остановка обработки событий"""
        self.running = False
        if self.processing_task:
            self.processing_task.cancel()
            try:
                await self.processing_task
            except asyncio.CancelledError:
                pass
        print("EventBus stopped")
    
    def subscribe(self, event_type: str, handler: Callable[[Event], Awaitable[None]]):
        """
        Подписка на события определенного типа
        
        Args:
            event_type: Тип события для подписки
            handler: Асинхронная функция-обработчик события
        """
        self.subscribers[event_type].append(handler)
        print(f"Subscribed to {event_type} events")
    
    def unsubscribe(self, event_type: str, handler: Callable[[Event], Awaitable[None]]):
        """Отписка от событий"""
        if event_type in self.subscribers:
            try:
                self.subscribers[event_type].remove(handler)
                print(f"Unsubscribed from {event_type} events")
            except ValueError:
                print(f"Handler not found for {event_type}")
    
    async def publish(self, event_type: str, data: Any, source: str = "unknown", metadata: Dict[str, Any] = None):
        """
        Публикация события
        
        Args:
            event_type: Тип события
            data: Данные события
            source: Источник события
            metadata: Дополнительные метаданные
        """
        event = Event(
            type=event_type,
            data=data,
            timestamp=datetime.now(),
            source=source,
            metadata=metadata or {}
        )
        
        # Добавление в историю
        self.event_history.append(event)
        if len(self.event_history) > self.max_history_size:
            self.event_history.pop(0)
        
        # Добавление в очередь обработки
        try:
            await self.event_queue.put(event)
        except asyncio.QueueFull:
            print(f"Event queue full, dropping event: {event_type}")
    
    async def _process_events(self):
        """Основной цикл обработки событий"""
        while self.running:
            try:
                # Получение события из очереди
                event = await asyncio.wait_for(self.event_queue.get(), timeout=1.0)
                
                # Уведомление всех подписчиков
                if event.type in self.subscribers:
                    tasks = []
                    for handler in self.subscribers[event.type]:
                        try:
                            task = asyncio.create_task(handler(event))
                            tasks.append(task)
                        except Exception as e:
                            print(f"Error creating task for event {event.type}: {e}")
                    
                    # Ожидание завершения всех обработчиков
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                
            except asyncio.TimeoutError:
                # Таймаут - нормальная ситуация
                continue
            except Exception as e:
                print(f"Error processing event: {e}")
                await asyncio.sleep(0.01)
    
    def get_subscribers_count(self, event_type: str = None) -> int:
        """Получение количества подписчиков"""
        if event_type:
            return len(self.subscribers.get(event_type, []))
        else:
            return sum(len(handlers) for handlers in self.subscribers.values())
    
    def get_event_history(self, event_type: str = None, limit: int = 100) -> List[Event]:
        """Получение истории событий"""
        if event_type:
            filtered_events = [e for e in self.event_history if e.type == event_type]
        else:
            filtered_events = self.event_history
        
        return filtered_events[-limit:]
    
    def get_statistics(self) -> Dict[str, Any]:
        """Получение статистики EventBus"""
        event_types = defaultdict(int)
        for event in self.event_history:
            event_types[event.type] += 1
        
        return {
            'total_events': len(self.event_history),
            'event_types': dict(event_types),
            'subscribers_count': self.get_subscribers_count(),
            'queue_size': self.event_queue.qsize(),
            'running': self.running
        }
    
    async def wait_for_event(self, event_type: str, timeout: float = 10.0) -> Event:
        """
        Ожидание события определенного типа
        
        Args:
            event_type: Тип ожидаемого события
            timeout: Таймаут ожидания в секундах
        
        Returns:
            Event: Полученное событие
            
        Raises:
            asyncio.TimeoutError: Если событие не получено в течение таймаута
        """
        future = asyncio.Future()
        
        async def event_handler(event: Event):
            if not future.done():
                future.set_result(event)
        
        self.subscribe(event_type, event_handler)
        
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        finally:
            self.unsubscribe(event_type, event_handler)
    
    def clear_history(self):
        """Очистка истории событий"""
        self.event_history.clear()
    
    def set_max_history_size(self, size: int):
        """Установка максимального размера истории"""
        self.max_history_size = max(1, size)
        # Обрезка истории если нужно
        while len(self.event_history) > self.max_history_size:
            self.event_history.pop(0)
