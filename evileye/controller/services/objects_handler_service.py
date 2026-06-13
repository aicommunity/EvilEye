"""Сервис управления ObjectsHandler."""

from __future__ import annotations

from typing import Any, Dict, Optional

from evileye.core.interfaces import IObjectHandler, IPipeline
from evileye.core.logger import get_module_logger
from evileye.objects_handler import objects_handler


class ObjectsHandlerService:
    """Сервис для управления ObjectsHandler: создание, инициализация, конфигурация."""

    def __init__(self, class_manager=None):
        """Инициализация сервиса.

        Args:
            class_manager: Менеджер классов для передачи в ObjectsHandler
        """
        self.logger = get_module_logger("objects_handler_service")
        self.class_manager = class_manager
        self._objects_handler: Optional[IObjectHandler] = None

    def create_objects_handler(
            self,
            db_controller: Optional[Any] = None,
            db_adapter: Optional[Any] = None,
    ) -> IObjectHandler:
        """Создать экземпляр ObjectsHandler.

        Args:
            db_controller: Контроллер БД (опционально)
            db_adapter: Адаптер БД для объектов (опционально)

        Returns:
            Экземпляр ObjectsHandler
        """
        self._objects_handler = objects_handler.ObjectsHandler(
            db_controller=db_controller,
            db_adapter=db_adapter,
        )
        self.logger.info("ObjectsHandler created")
        return self._objects_handler

    def initialize_objects_handler(
            self,
            objects_handler: IObjectHandler,
            params: Dict[str, Any],
            pipeline: Optional[IPipeline] = None,
    ) -> IObjectHandler:
        """Инициализировать ObjectsHandler с параметрами.

        Args:
            objects_handler: Экземпляр ObjectsHandler для инициализации (соответствует IObjectHandler)
            params: Параметры конфигурации
            pipeline: Pipeline для получения параметров камер (опционально, соответствует IPipeline)

        Returns:
            Инициализированный ObjectsHandler
        """
        # Protocol compliance: IPipeline гарантирует наличие метода get_sources()
        # Установить параметры камер из pipeline, если доступен
        if pipeline:
            sources = pipeline.get_sources()
            if sources:
                cameras_params = []
                for source in sources:
                    if (hasattr(source, 'source_ids') and hasattr(source, 'source_names') and
                            source.source_ids and source.source_names):
                        camera_param = {
                            'source_ids': source.source_ids,
                            'source_names': source.source_names,
                            'camera': getattr(source, 'camera', '')
                        }
                        cameras_params.append(camera_param)

                # Установить параметры камер через инкапсулированный API
                try:
                    objects_handler.set_cameras_params(cameras_params)
                except Exception:
                    # Fallback для старого API
                    try:
                        objects_handler.cameras_params = cameras_params
                    except Exception:
                        pass

        # Установить параметры
        safe_params = params or {}
        objects_handler.set_params(**safe_params)

        # Установить class manager
        if self.class_manager:
            objects_handler.class_manager = self.class_manager

        # Инициализировать
        objects_handler.init()

        self._objects_handler = objects_handler
        self.logger.info("ObjectsHandler initialized")
        return objects_handler

    def get_objects_handler(self) -> Optional[IObjectHandler]:
        """Получить текущий ObjectsHandler.

        Returns:
            Текущий ObjectsHandler или None
        """
        return self._objects_handler

    def start_objects_handler(self) -> None:
        """Запустить ObjectsHandler."""
        if self._objects_handler:
            self._objects_handler.start()
            self.logger.info("ObjectsHandler started")
        else:
            self.logger.warning("Cannot start ObjectsHandler: not initialized")

    def stop_objects_handler(self) -> None:
        """Остановить ObjectsHandler."""
        if self._objects_handler:
            self._objects_handler.stop()
            self.logger.info("ObjectsHandler stopped")

    def release_objects_handler(self) -> None:
        """Освободить ресурсы ObjectsHandler."""
        if self._objects_handler:
            self._objects_handler.stop()
            self._objects_handler = None
            self.logger.info("ObjectsHandler released")
