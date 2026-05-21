"""Определения зависимостей для Dependency Injection.

Этот модуль предоставляет реестр определений зависимостей для системы
Dependency Injection. Реестр хранит метаданные о зависимостях (тип сервиса,
фабрика создания, singleton-флаг и т.д.) и используется вместе с `DIContainer`
для управления жизненным циклом сервисов.

Статус: зарезервировано для будущего использования
-------------------------------------------

В текущей версии EvilEye зависимости создаются напрямую в сервисах контроллера
или через `EvilEyeBase._registry` для компонентов pipeline.

`DependencyRegistry` планируется использовать для:
- Централизованной регистрации всех зависимостей системы
- Хранения метаданных о зависимостях (singleton, factory, scope)
- Интеграции с `DIContainer` для автоматического создания сервисов
- Упрощения конфигурации и инициализации системы

Связь с DIContainer:
- `DependencyRegistry` хранит определения зависимостей (что создавать, как создавать)
- `DIContainer` использует эти определения для создания и кеширования экземпляров
- Глобальный реестр (`get_registry()`, `register_dependency()`) позволяет
  регистрировать зависимости в одном месте и использовать их через контейнер

Пример планируемого использования:
    registry = get_registry()
    registry.register(IPipeline, factory=create_pipeline, singleton=True)
    registry.register(IDatabaseService, factory=create_db_service, singleton=True)
    
    container = DIContainer()
    # Контейнер использует registry для создания сервисов
"""

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
            capabilities: Optional[Dict[str, Any]] = None,
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
        self.capabilities = capabilities or {}


# TODO: Планируется интеграция в будущих версиях для снижения связности
# между компонентами. В текущей версии используется EvilEyeBase._registry
# как основной механизм создания компонентов.
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
            capabilities: Optional[Dict[str, Any]] = None,
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
            capabilities=capabilities,
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
        capabilities: Optional[Dict[str, Any]] = None,
) -> None:
    """Зарегистрировать зависимость в глобальном реестре.

    Args:
        service_type: Тип сервиса
        factory: Фабрика для создания
        instance: Готовый экземпляр
        singleton: Создавать ли один экземпляр
    """
    _global_registry.register(
        service_type,
        factory,
        instance,
        singleton,
        capabilities=capabilities,
    )
