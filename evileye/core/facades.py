"""Фасады для упрощения работы с подсистемами."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evileye.core.interfaces import IDatabaseAdapter, IPipeline, IVisualizer


class PipelineFacade:
    """Фасад для упрощенной работы с pipeline."""

    def __init__(self, pipeline: IPipeline):
        """Инициализация фасада.

        Args:
            pipeline: Pipeline для работы
        """
        self._pipeline = pipeline

    def process_frame(self) -> Dict[str, Any]:
        """Обработать один кадр через pipeline.

        Returns:
            Результаты обработки
        """
        return self._pipeline.process()

    def get_sources(self) -> List[Any]:
        """Получить источники видео.

        Returns:
            Список источников
        """
        return self._pipeline.get_sources()

    def get_latest_results(self) -> Optional[Dict[str, Any]]:
        """Получить последние результаты обработки.

        Returns:
            Последние результаты или None
        """
        return self._pipeline.get_current_results()

    def is_running(self) -> bool:
        """Проверить, запущен ли pipeline.

        Returns:
            True если запущен
        """
        # Проверка через наличие результатов или другие индикаторы
        return self._pipeline.get_current_results() is not None


class DatabaseFacade:
    """Фасад для упрощенной работы с БД."""

    def __init__(self, adapters: Dict[str, IDatabaseAdapter]):
        """Инициализация фасада.

        Args:
            adapters: Словарь адаптеров {имя: адаптер}
        """
        self._adapters = adapters

    def save_object(self, object_data: Dict[str, Any]) -> None:
        """Сохранить объект в БД.

        Args:
            object_data: Данные объекта
        """
        adapter = self._adapters.get('DatabaseAdapterObjects')
        if adapter:
            adapter.insert(object_data)

    def save_event(self, event_name: str, event_data: Dict[str, Any]) -> None:
        """Сохранить событие в БД.

        Args:
            event_name: Имя события
            event_data: Данные события
        """
        # Поиск адаптера по имени события
        for name, adapter in self._adapters.items():
            if adapter.get_event_name() == event_name:
                adapter.insert(event_data)
                return

    def get_adapter(self, adapter_name: str) -> Optional[IDatabaseAdapter]:
        """Получить адаптер по имени.

        Args:
            adapter_name: Имя адаптера

        Returns:
            Адаптер или None
        """
        return self._adapters.get(adapter_name)
