"""Пул объектов для переиспользования и оптимизации памяти."""

from __future__ import annotations

from collections import deque
from threading import Lock
from typing import Generic, Optional, TypeVar

T = TypeVar('T')


class ObjectPool(Generic[T]):
    """Пул объектов для переиспользования.

    Уменьшает количество выделений памяти за счет переиспользования объектов.
    """

    def __init__(self, factory: callable, max_size: int = 10, reset_func: Optional[callable] = None):
        """Инициализация пула.

        Args:
            factory: Функция для создания новых объектов
            max_size: Максимальный размер пула
            reset_func: Функция для сброса состояния объекта перед переиспользованием
        """
        self._factory = factory
        self._max_size = max_size
        self._reset_func = reset_func
        self._pool: deque[T] = deque(maxlen=max_size)
        self._lock = Lock()

    def acquire(self) -> T:
        """Получить объект из пула или создать новый.

        Returns:
            Объект из пула
        """
        with self._lock:
            if self._pool:
                obj = self._pool.popleft()
                if self._reset_func:
                    self._reset_func(obj)
                return obj
            return self._factory()

    def release(self, obj: T) -> None:
        """Вернуть объект в пул.

        Args:
            obj: Объект для возврата в пул
        """
        with self._lock:
            if len(self._pool) < self._max_size:
                self._pool.append(obj)

    def clear(self) -> None:
        """Очистить пул."""
        with self._lock:
            self._pool.clear()
