"""Обработчик ошибок базы данных."""

from __future__ import annotations

from typing import Optional, Callable, Any
import time
import psycopg2
from psycopg2 import errors
from ..core.logger import get_module_logger


class DatabaseErrorHandler:
    """Единый обработчик ошибок базы данных."""

    def __init__(self, logger=None):
        """Инициализация обработчика ошибок.

        Args:
            logger: Логгер для записи ошибок. Если не указан, создается новый.
        """
        self.logger = logger or get_module_logger("database_error_handler")

    def handle_query_error(
            self,
            error: Exception,
            query_string: Optional[str] = None,
            retry_callback: Optional[Callable[[], Any]] = None,
            max_retries: int = 1,
    ) -> tuple[bool, Optional[Exception]]:
        """Обработать ошибку запроса к БД.

        Args:
            error: Исключение, которое произошло
            query_string: SQL запрос (для логирования)
            retry_callback: Функция для повторной попытки (опционально)
            max_retries: Максимальное количество повторных попыток

        Returns:
            Кортеж (should_retry, last_error)
        """
        error_msg = str(error)

        # Ошибка отсутствующей колонки (автомиграция)
        if self._is_missing_column_error(error_msg):
            self.logger.warning(
                f"Missing column detected: {error_msg}. "
                "This may trigger auto-migration."
            )
            if retry_callback and max_retries > 0:
                try:
                    retry_callback()
                    self.logger.info("Auto-migration successful, retrying query")
                    return True, None
                except Exception as retry_error:
                    self.logger.error(
                        f"Auto-migration failed: {retry_error}. "
                        f"Original error: {error}"
                    )
                    return False, retry_error
            return True, error

        if isinstance(error, psycopg2.OperationalError):
            self.logger.error(
                f"Database operational error: {error}. "
                f"Query: {query_string if query_string else 'N/A'}"
            )
            if retry_callback and max_retries > 0:
                return True, error
            return False, error

        if isinstance(error, psycopg2.ProgrammingError):
            self.logger.error(
                f"Database programming error: {error}. "
                f"Query: {query_string if query_string else 'N/A'}"
            )
            return False, error

        if isinstance(error, psycopg2.IntegrityError):
            self.logger.error(
                f"Database integrity error: {error}. "
                f"Query: {query_string if query_string else 'N/A'}"
            )
            return False, error

        if isinstance(error, psycopg2.Error):
            self.logger.error(
                f"Database error: {error}. "
                f"Query: {query_string if query_string else 'N/A'}"
            )
            return False, error

        self.logger.error(
            f"Unexpected error during database operation: {error}. "
            f"Query: {query_string if query_string else 'N/A'}",
            exc_info=True,
        )
        return False, error

    def _is_missing_column_error(self, error_msg: str) -> bool:
        """Проверить, является ли ошибка ошибкой отсутствующей колонки."""
        missing_column_indicators = [
            "UndefinedColumn",
            "does not exist",
            "column",
            "не существует",
        ]
        error_lower = error_msg.lower()
        return any(indicator.lower() in error_lower for indicator in missing_column_indicators)

    def execute_with_retry(
            self,
            func: Callable[[], Any],
            max_retries: int = 3,
            initial_delay: float = 0.1,
            max_delay: float = 2.0,
            exponential_base: float = 2.0,
            retryable_errors: Optional[tuple[type[Exception], ...]] = None,
    ) -> tuple[Optional[Any], Optional[Exception]]:
        """Выполнить функцию с повторными попытками при ошибках."""
        if retryable_errors is None:
            retryable_errors = (psycopg2.OperationalError,)

        last_error = None
        delay = initial_delay

        for attempt in range(max_retries):
            try:
                result = func()
                if attempt > 0:
                    self.logger.info(
                        f"Database operation succeeded after {attempt} retries"
                    )
                return result, None
            except Exception as e:
                last_error = e

                if not isinstance(e, retryable_errors):
                    self.logger.debug(
                        f"Error is not retryable: {type(e).__name__}. "
                        f"Not retrying."
                    )
                    return None, e

                if attempt < max_retries - 1:
                    self.logger.warning(
                        f"Database operation failed (attempt {attempt + 1}/{max_retries}): {e}. "
                        f"Retrying in {delay:.2f}s..."
                    )
                    time.sleep(delay)
                    delay = min(delay * exponential_base, max_delay)
                else:
                    self.logger.error(
                        f"Database operation failed after {max_retries} attempts: {e}"
                    )

        return None, last_error
