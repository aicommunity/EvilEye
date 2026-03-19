"""Сервис управления базой данных и адаптерами."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from evileye.core.interfaces import IDatabaseAdapter
from evileye.core.logger import get_module_logger
from evileye.database_controller.database_controller_pg import DatabaseControllerPg
from evileye.database_controller.db_adapter_objects import DatabaseAdapterObjects
from evileye.database_controller.db_adapter_cam_events import DatabaseAdapterCamEvents
from evileye.database_controller.db_adapter_fov_events import DatabaseAdapterFieldOfViewEvents
from evileye.database_controller.db_adapter_zone_events import DatabaseAdapterZoneEvents
from evileye.database_controller.db_adapter_system_events import DatabaseAdapterSystemEvents
from evileye.database_controller.db_adapter_attribute_events import DatabaseAdapterAttributeEvents
from evileye.database_controller.migrations import apply_startup_migrations


class DatabaseService:
    """Сервис для управления подключением к БД и адаптерами."""

    def __init__(self):
        """Инициализация сервиса."""
        self.logger = get_module_logger("database_service")
        self._db_controller: Optional[DatabaseControllerPg] = None
        self._adapters: Dict[str, IDatabaseAdapter] = {}

    def initialize_database(
        self,
        db_config: Dict[str, Any],
        system_params: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Инициализировать подключение к БД.

        Args:
            db_config: Конфигурация БД
            system_params: Системные параметры

        Returns:
            True если подключение успешно, False иначе
        """
        try:
            self._db_controller = DatabaseControllerPg(system_params or {})
            self._db_controller.set_params(**db_config)
            self._db_controller.init()

            # Попытка подключения
            self._db_controller.connect()
            if not self._db_controller.is_connected():
                self.logger.warning("Database connection failed during initialization")
                self._db_controller = None
                return False

            # Apply idempotent schema migrations once at startup.
            # This keeps DDL out of adapters / GUI read paths.
            try:
                apply_startup_migrations(self._db_controller, logger=self.logger)
            except Exception as e:
                self.logger.warning(f"Failed to apply startup migrations: {e}")

            self.logger.info("Database connected successfully")
            return True
        except Exception as e:
            self.logger.warning(f"Database initialization failed: {e}")
            self._db_controller = None
            return False

    def initialize_adapters(self, adapters_config: Dict[str, Dict[str, Any]]) -> None:
        """Инициализировать адаптеры БД.

        Args:
            adapters_config: Конфигурация адаптеров {имя_класса: параметры}
        """
        if not self._db_controller:
            self.logger.warning("Cannot initialize adapters: database controller not initialized")
            return

        adapter_classes = {
            'DatabaseAdapterObjects': DatabaseAdapterObjects,
            'DatabaseAdapterCamEvents': DatabaseAdapterCamEvents,
            'DatabaseAdapterFieldOfViewEvents': DatabaseAdapterFieldOfViewEvents,
            'DatabaseAdapterZoneEvents': DatabaseAdapterZoneEvents,
            'DatabaseAdapterAttributeEvents': DatabaseAdapterAttributeEvents,
            'DatabaseAdapterSystemEvents': DatabaseAdapterSystemEvents,
        }

        for adapter_name, adapter_class in adapter_classes.items():
            if adapter_name in adapters_config:
                try:
                    adapter = adapter_class(self._db_controller)
                    adapter.set_params(**adapters_config[adapter_name])
                    adapter.init()
                    self._adapters[adapter_name] = adapter
                    self.logger.debug(f"Initialized adapter: {adapter_name}")
                except Exception as e:
                    self.logger.error(f"Failed to initialize adapter {adapter_name}: {e}")

    def get_db_controller(self) -> Optional[DatabaseControllerPg]:
        """Получить контроллер БД.

        Returns:
            Контроллер БД или None
        """
        return self._db_controller

    def get_adapter(self, adapter_name: str) -> Optional[IDatabaseAdapter]:
        """Получить адаптер по имени.

        Args:
            adapter_name: Имя адаптера

        Returns:
            Адаптер или None
        """
        return self._adapters.get(adapter_name)

    def get_all_adapters(self) -> Dict[str, IDatabaseAdapter]:
        """Получить все адаптеры.

        Returns:
            Словарь {имя: адаптер}
        """
        return self._adapters.copy()

    def start_adapters(self) -> None:
        """Запустить все адаптеры."""
        for name, adapter in self._adapters.items():
            try:
                adapter.start()
                self.logger.debug(f"Started adapter: {name}")
            except Exception as e:
                self.logger.error(f"Failed to start adapter {name}: {e}")

    def stop_adapters(self) -> None:
        """Остановить все адаптеры."""
        for name, adapter in self._adapters.items():
            try:
                adapter.stop()
                self.logger.debug(f"Stopped adapter: {name}")
            except Exception as e:
                self.logger.error(f"Failed to stop adapter {name}: {e}")

    def is_connected(self) -> bool:
        """Проверить подключение к БД.

        Returns:
            True если подключено, False иначе
        """
        return self._db_controller is not None and self._db_controller.is_connected()

    def release(self) -> None:
        """Освободить ресурсы БД и адаптеров."""
        self.stop_adapters()
        if self._db_controller:
            self._db_controller = None
        self._adapters.clear()
        self.logger.info("Database service released")
