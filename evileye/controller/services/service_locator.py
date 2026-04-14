"""Service Locator для управления сервисами контроллера."""

from __future__ import annotations

from typing import Optional
from evileye.core.di_container import DIContainer

from evileye.controller.services.config_service import ConfigurationService
from evileye.controller.services.database_service import DatabaseService
from evileye.controller.services.events_service import EventsService
from evileye.controller.services.objects_handler_service import ObjectsHandlerService
from evileye.controller.services.pipeline_service import PipelineService
from evileye.controller.services.preview_render_service import PreviewRenderService
from evileye.controller.services.streaming_service import StreamingService
from evileye.controller.services.visualization_service import VisualizationService


class ServiceLocator:
    """Локатор сервисов для централизованного управления зависимостями."""

    def __init__(self):
        """Инициализация локатора сервисов."""
        self._container = DIContainer()
        self._pipeline_service: Optional[PipelineService] = None
        self._database_service: Optional[DatabaseService] = None
        self._events_service: Optional[EventsService] = None
        self._visualization_service: Optional[VisualizationService] = None
        self._config_service: Optional[ConfigurationService] = None
        self._objects_handler_service: Optional[ObjectsHandlerService] = None
        self._streaming_service: Optional[StreamingService] = None
        self._preview_render_service: Optional[PreviewRenderService] = None

    def register_pipeline_service(self, service: PipelineService) -> None:
        """Зарегистрировать сервис pipeline.

        Args:
            service: Сервис pipeline
        """
        self._pipeline_service = service
        self._container.register_instance(PipelineService, service)

    def register_database_service(self, service: DatabaseService) -> None:
        """Зарегистрировать сервис БД.

        Args:
            service: Сервис БД
        """
        self._database_service = service
        self._container.register_instance(DatabaseService, service)

    def register_events_service(self, service: EventsService) -> None:
        """Зарегистрировать сервис событий.

        Args:
            service: Сервис событий
        """
        self._events_service = service
        self._container.register_instance(EventsService, service)

    def register_visualization_service(self, service: VisualizationService) -> None:
        """Зарегистрировать сервис визуализации.

        Args:
            service: Сервис визуализации
        """
        self._visualization_service = service
        self._container.register_instance(VisualizationService, service)

    def register_config_service(self, service: ConfigurationService) -> None:
        """Зарегистрировать сервис конфигурации.

        Args:
            service: Сервис конфигурации
        """
        self._config_service = service
        self._container.register_instance(ConfigurationService, service)

    def get_pipeline_service(self) -> Optional[PipelineService]:
        """Получить сервис pipeline.

        Returns:
            Сервис pipeline или None
        """
        return self._pipeline_service

    def get_database_service(self) -> Optional[DatabaseService]:
        """Получить сервис БД.

        Returns:
            Сервис БД или None
        """
        return self._database_service

    def get_events_service(self) -> Optional[EventsService]:
        """Получить сервис событий.

        Returns:
            Сервис событий или None
        """
        return self._events_service

    def get_visualization_service(self) -> Optional[VisualizationService]:
        """Получить сервис визуализации.

        Returns:
            Сервис визуализации или None
        """
        return self._visualization_service

    def get_config_service(self) -> Optional[ConfigurationService]:
        """Получить сервис конфигурации.

        Returns:
            Сервис конфигурации или None
        """
        return self._config_service

    def register_streaming_service(self, service: StreamingService) -> None:
        self._streaming_service = service
        self._container.register_instance(StreamingService, service)

    def get_streaming_service(self) -> Optional[StreamingService]:
        return self._streaming_service

    def register_preview_render_service(self, service: PreviewRenderService) -> None:
        self._preview_render_service = service
        self._container.register_instance(PreviewRenderService, service)

    def get_preview_render_service(self) -> Optional[PreviewRenderService]:
        return self._preview_render_service

    def register_objects_handler_service(self, service: ObjectsHandlerService) -> None:
        """Зарегистрировать сервис ObjectsHandler.

        Args:
            service: Сервис ObjectsHandler
        """
        self._objects_handler_service = service
        self._container.register_instance(ObjectsHandlerService, service)

    def get_objects_handler_service(self) -> Optional[ObjectsHandlerService]:
        """Получить сервис ObjectsHandler.

        Returns:
            Сервис ObjectsHandler или None
        """
        return self._objects_handler_service

    def create_all_services(self, class_manager=None) -> None:
        """Создать все сервисы с дефолтными настройками.

        Args:
            class_manager: Менеджер классов для передачи в сервисы
        """
        if not self._container.has(PipelineService):
            self._container.register_singleton(
                PipelineService, lambda: PipelineService(class_manager=class_manager)
            )
        if not self._container.has(DatabaseService):
            self._container.register_singleton(DatabaseService, DatabaseService)
        if not self._container.has(EventsService):
            self._container.register_singleton(EventsService, EventsService)
        if not self._container.has(VisualizationService):
            self._container.register_singleton(VisualizationService, VisualizationService)
        if not self._container.has(ConfigurationService):
            self._container.register_singleton(ConfigurationService, ConfigurationService)
        if not self._container.has(ObjectsHandlerService):
            self._container.register_singleton(
                ObjectsHandlerService, lambda: ObjectsHandlerService(class_manager=class_manager)
            )
        if not self._container.has(StreamingService):
            self._container.register_singleton(StreamingService, StreamingService)
        if not self._container.has(PreviewRenderService):
            self._container.register_singleton(PreviewRenderService, PreviewRenderService)

        self._pipeline_service = self._container.get(PipelineService)
        self._database_service = self._container.get(DatabaseService)
        self._events_service = self._container.get(EventsService)
        self._visualization_service = self._container.get(VisualizationService)
        self._config_service = self._container.get(ConfigurationService)
        self._objects_handler_service = self._container.get(ObjectsHandlerService)
        self._streaming_service = self._container.get(StreamingService)
        self._preview_render_service = self._container.get(PreviewRenderService)

    def release_all(self) -> None:
        """Освободить все сервисы."""
        if self._pipeline_service:
            self._pipeline_service.release_pipeline()
        if self._database_service:
            self._database_service.release()
        if self._events_service:
            self._events_service.release()
        if self._visualization_service:
            self._visualization_service.release()
        if self._objects_handler_service:
            self._objects_handler_service.release_objects_handler()
        if self._streaming_service:
            self._streaming_service.stop()
        if self._preview_render_service:
            self._preview_render_service.stop()
