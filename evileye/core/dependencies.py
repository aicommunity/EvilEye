"""Определения зависимостей для Dependency Injection."""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type

from evileye.core.interfaces import (
    IDatabaseAdapter,
    IEventDetector,
    IObjectHandler,
    IPipeline,
    IVisualizer,
)


class DependencyDefinition:
    """Определение зависимости для DI контейнера."""

    def __init__(
        self,
        service_type: Type,
        factory: Optional[Callable[[], Any]] = None,
        instance: Optional[Any] = None,
        singleton: bool = True,
    ):
        """Инициализация определения зависимости.

        Args:
            service_type: Тип сервиса (интерфейс или класс)
            factory: Фабрика для создания экземпляра
            instance: Готовый экземпляр (для singleton)
            singleton: Создавать ли один экземпляр на все запросы
        """
        self.service_type = service_type
        self.factory = factory
        self.instance = instance
        self.singleton = singleton


class DependencyRegistry:
    """Реестр зависимостей для системы."""

    def __init__(self):
        """Инициализация реестра."""
        self._definitions: Dict[Type, DependencyDefinition] = {}

    def register(
        self,
        service_type: Type,
        factory: Optional[Callable[[], Any]] = None,
        instance: Optional[Any] = None,
        singleton: bool = True,
    ) -> None:
        """Зарегистрировать зависимость.

        Args:
            service_type: Тип сервиса
            factory: Фабрика для создания
            instance: Готовый экземпляр
            singleton: Создавать ли один экземпляр
        """
        self._definitions[service_type] = DependencyDefinition(
            service_type=service_type,
            factory=factory,
            instance=instance,
            singleton=singleton,
        )

    def get_definition(self, service_type: Type) -> Optional[DependencyDefinition]:
        """Получить определение зависимости.

        Args:
            service_type: Тип сервиса

        Returns:
            Определение зависимости или None
        """
        return self._definitions.get(service_type)

    def has(self, service_type: Type) -> bool:
        """Проверить наличие зависимости.

        Args:
            service_type: Тип сервиса

        Returns:
            True если зарегистрирована
        """
        return service_type in self._definitions

    def clear(self) -> None:
        """Очистить реестр."""
        self._definitions.clear()


# Глобальный реестр зависимостей
_global_registry = DependencyRegistry()


def get_registry() -> DependencyRegistry:
    """Получить глобальный реестр зависимостей.

    Returns:
        Глобальный реестр
    """
    return _global_registry


def register_dependency(
    service_type: Type,
    factory: Optional[Callable[[], Any]] = None,
    instance: Optional[Any] = None,
    singleton: bool = True,
) -> None:
    """Зарегистрировать зависимость в глобальном реестре.

    Args:
        service_type: Тип сервиса
        factory: Фабрика для создания
        instance: Готовый экземпляр
        singleton: Создавать ли один экземпляр
    """
    _global_registry.register(service_type, factory, instance, singleton)
