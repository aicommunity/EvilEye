"""Валидатор для операций с базой данных."""

from __future__ import annotations

from typing import Any, Optional, List
from ..core.logger import get_module_logger


class DatabaseValidator:
    """Валидатор для проверки входных данных перед операциями с БД."""

    def __init__(self, logger=None):
        """Инициализация валидатора.

        Args:
            logger: Логгер для записи ошибок. Если не указан, создается новый.
        """
        self.logger = logger or get_module_logger("database_validator")

    def validate_insert_params(
            self,
            table_name: Optional[str],
            fields: Optional[List[str]],
            data: Optional[Any],
    ) -> tuple[bool, Optional[str]]:
        """Валидировать параметры для операции INSERT.

        Args:
            table_name: Имя таблицы
            fields: Список полей
            data: Данные для вставки

        Returns:
            Кортеж (is_valid, error_message):
            - is_valid: True если данные валидны
            - error_message: Сообщение об ошибке или None
        """
        if not table_name:
            return False, "Table name is required for INSERT operation"

        if not fields:
            return False, "Fields list is required for INSERT operation"

        if not isinstance(fields, (list, tuple)):
            return False, f"Fields must be a list or tuple, got {type(fields)}"

        if len(fields) == 0:
            return False, "Fields list cannot be empty"

        if data is None:
            return False, "Data is required for INSERT operation"

        # Проверяем соответствие количества полей и данных
        if isinstance(data, (list, tuple)):
            if len(fields) != len(data):
                return False, (
                    f"Fields count ({len(fields)}) does not match "
                    f"data count ({len(data)})"
                )

        return True, None

    def validate_update_params(
            self,
            table_name: Optional[str],
            fields: Optional[List[str]],
            data: Optional[Any],
            obj_id: Optional[Any],
    ) -> tuple[bool, Optional[str]]:
        """Валидировать параметры для операции UPDATE.

        Args:
            table_name: Имя таблицы
            fields: Список полей для обновления
            data: Данные для обновления
            obj_id: ID объекта для обновления

        Returns:
            Кортеж (is_valid, error_message):
            - is_valid: True если данные валидны
            - error_message: Сообщение об ошибке или None
        """
        if not table_name:
            return False, "Table name is required for UPDATE operation"

        if not fields:
            return False, "Fields list is required for UPDATE operation"

        if not isinstance(fields, (list, tuple)):
            return False, f"Fields must be a list or tuple, got {type(fields)}"

        if len(fields) == 0:
            return False, "Fields list cannot be empty"

        if data is None:
            return False, "Data is required for UPDATE operation"

        if obj_id is None:
            return False, "Object ID is required for UPDATE operation"

        # Проверяем соответствие количества полей и данных
        if isinstance(data, (list, tuple)):
            if len(fields) != len(data):
                return False, (
                    f"Fields count ({len(fields)}) does not match "
                    f"data count ({len(data)})"
                )

        return True, None

    def validate_table_name(self, table_name: Optional[str]) -> tuple[bool, Optional[str]]:
        """Валидировать имя таблицы.

        Args:
            table_name: Имя таблицы

        Returns:
            Кортеж (is_valid, error_message)
        """
        if not table_name:
            return False, "Table name cannot be empty"

        if not isinstance(table_name, str):
            return False, f"Table name must be a string, got {type(table_name)}"

        # Простая проверка на безопасность имени таблицы
        if not table_name.replace("_", "").replace("-", "").isalnum():
            return False, (
                f"Table name contains invalid characters: {table_name}. "
                "Only alphanumeric characters, underscores and hyphens are allowed"
            )

        return True, None
