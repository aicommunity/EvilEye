"""Dependency Injection контейнер для управления зависимостями.

Этот модуль предоставляет контейнер для управления зависимостями через паттерн
Dependency Injection (DI). Контейнер позволяет регистрировать сервисы, фабрики
и singleton-объекты, а затем получать их по типу.

Статус: зарезервировано для будущего использования
-------------------------------------------

В текущей версии EvilEye используется `EvilEyeBase._registry` с декоратором
`@EvilEyeBase.register` как основной механизм создания компонентов (plugin-фабрика).
Этот подход активно используется в 11+ классах проекта.

`DIContainer` планируется интегрировать в будущих версиях для:
- Снижения связности между компонентами
- Упрощения тестирования (возможность подмены зависимостей)
- Централизованного управления жизненным циклом сервисов
- Замены прямого создания объектов в services на DI

Связь с EvilEyeBase._registry:
- `EvilEyeBase._registry` остается основным механизмом для создания компонентов
  pipeline (детекторы, трекеры, процессоры и т.д.)
- `DIContainer` планируется использовать для управления сервисами верхнего уровня
  (PipelineService, DatabaseService, EventsService и т.д.)
- Оба механизма могут сосуществовать: `EvilEyeBase` для компонентов pipeline,
  `DIContainer` для сервисов контроллера

Пример планируемого использования:
    container = DIContainer()
    container.register_factory(IPipeline, lambda: create_pipeline())
    container.register_singleton(IDatabaseService, lambda: DatabaseService())
    
    # В сервисах:
    pipeline = container.get(IPipeline)
    db_service = container.get(IDatabaseService)
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional, Type, TypeVar

T = TypeVar('T')


# TODO: Планируется интеграция в будущих версиях для снижения связности
# между компонентами. В текущей версии используется EvilEyeBase._registry
# как основной механизм создания компонентов.
class DIContainer:
    """Контейнер для управления зависимостями через Dependency Injection."""

    def __init__(self):
        """Инициализация контейнера."""
        self._services: Dict[Type, Any] = {}
        self._factories: Dict[Type, Callable[[], Any]] = {}
        self._singletons: Dict[Type, Any] = {}

    def register_instance(self, service_type: Type[T], instance: T) -> None:
        """Зарегистрировать экземпляр сервиса.

        Args:
            service_type: Тип сервиса
            instance: Экземпляр сервиса
        """
        self._services[service_type] = instance
        self._singletons[service_type] = instance

    def register_factory(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Зарегистрировать фабрику для создания сервиса.

        Args:
            service_type: Тип сервиса
            factory: Функция-фабрика для создания экземпляра
        """
        self._factories[service_type] = factory

    def register_singleton(self, service_type: Type[T], factory: Callable[[], T]) -> None:
        """Зарегистрировать singleton фабрику.

        Args:
            service_type: Тип сервиса
            factory: Функция-фабрика для создания экземпляра (вызывается один раз)
        """
        self._factories[service_type] = factory
        # Singleton будет создан при первом запросе

    def get(self, service_type: Type[T]) -> Optional[T]:
        """Получить сервис по типу.

        Args:
            service_type: Тип сервиса

        Returns:
            Экземпляр сервиса или None
        """
        # Проверка зарегистрированного экземпляра
        if service_type in self._services:
            return self._services[service_type]

        # Проверка singleton
        if service_type in self._singletons:
            return self._singletons[service_type]

        # Проверка фабрики
        if service_type in self._factories:
            factory = self._factories[service_type]
            instance = factory()

            # Если это singleton, сохранить для повторного использования
            if service_type in self._factories:
                # Проверяем, не был ли уже создан singleton
                if service_type not in self._singletons:
                    self._singletons[service_type] = instance

            return instance

        return None

    def get_or_create(self, service_type: Type[T], default_factory: Callable[[], T]) -> T:
        """Получить сервис или создать его через фабрику по умолчанию.

        Args:
            service_type: Тип сервиса
            default_factory: Фабрика по умолчанию, если сервис не зарегистрирован

        Returns:
            Экземпляр сервиса
        """
        instance = self.get(service_type)
        if instance is None:
            instance = default_factory()
            self.register_instance(service_type, instance)
        return instance

    def has(self, service_type: Type[T]) -> bool:
        """Проверить, зарегистрирован ли сервис.

        Args:
            service_type: Тип сервиса

        Returns:
            True если зарегистрирован
        """
        return (
                service_type in self._services or
                service_type in self._factories or
                service_type in self._singletons
        )

    def clear(self) -> None:
        """Очистить все зарегистрированные сервисы."""
        self._services.clear()
        self._factories.clear()
        self._singletons.clear()
