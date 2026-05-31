from __future__ import annotations

from typing import Any, Optional, Dict
from ..core.base_class import EvilEyeBase
from ..core.interfaces import IDatabaseAdapter
from .database_controller_pg import DatabaseControllerPg
from .database_error_handler import DatabaseErrorHandler
from threading import Thread
from queue import Queue, Empty
from abc import abstractmethod, ABC


class DatabaseAdapterBase(EvilEyeBase, ABC):
    def __init__(self, db_controller: DatabaseControllerPg):
        super().__init__()
        self.db_controller: DatabaseControllerPg = db_controller
        self.db_params: Dict[str, Any] = self.db_controller.get_params()
        self.cameras_params: Dict[str, Any] = self.db_controller.get_cameras_params()
        self.query_thread: Thread = Thread(target=self._execute_query)
        self.run_flag: bool = False
        self.queue_in: Queue = Queue()
        self.table_name: Optional[str] = None
        self.event_name: Optional[str] = None
        # Батчинг: размер батча и таймаут для сбора запросов (секунды)
        self.batch_size: int = 10  # По умолчанию батчинг отключен (batch_size=1 означает обработку по одному)
        self.batch_timeout: float = 0.1  # Максимальное время ожидания для формирования батча
        # Обработчик ошибок
        self.error_handler: DatabaseErrorHandler = DatabaseErrorHandler(logger=self.logger)

    def set_params_impl(self) -> None:
        self.table_name = self.params['table_name']
        # Параметры батчинга (опционально)
        self.batch_size = self.params.get('batch_size', 10)
        self.batch_timeout = self.params.get('batch_timeout', 0.1)

    def get_params_impl(self) -> Dict[str, Any]:
        params: Dict[str, Any] = dict()
        params['table_name'] = self.table_name
        return params

    def init_impl(self) -> None:
        pass

    def get_event_name(self) -> Optional[str]:
        return self.event_name

    def get_table_name(self) -> Optional[str]:
        return self.table_name

    def start(self) -> None:
        self.run_flag = True
        self.query_thread.start()

    def stop(self) -> None:
        self.run_flag = False
        if self.query_thread.is_alive():
            self.query_thread.join()

    def default(self) -> None:
        pass

    def reset_impl(self) -> None:
        pass

    def release_impl(self) -> None:
        pass

    def insert(self, data: Any) -> None:
        # Проверяем, что БД подключена перед выполнением операций (только для БД адаптеров)
        # JSON адаптеры не имеют db_controller с методом is_connected(), поэтому проверяем наличие метода
        if self.db_controller and hasattr(self.db_controller, 'is_connected'):
            if not self.db_controller.is_connected():
                return  # БД недоступна, просто игнорируем операцию
        # Для JSON адаптеров (db_controller может быть None или self) всегда выполняем операцию
        self._insert_impl(data)

    def update(self, data: Any) -> None:
        # Проверяем, что БД подключена перед выполнением операций (только для БД адаптеров)
        # JSON адаптеры не имеют db_controller с методом is_connected(), поэтому проверяем наличие метода
        if self.db_controller and hasattr(self.db_controller, 'is_connected'):
            if not self.db_controller.is_connected():
                return  # БД недоступна, просто игнорируем операцию
        # Для JSON адаптеров (db_controller может быть None или self) всегда выполняем операцию
        self._update_impl(data)

    def get_db_params(self) -> Dict[str, Any]:
        return self.db_params

    def get_cameras_params(self) -> Dict[str, Any]:
        return self.cameras_params

    def _execute_query(self) -> None:
        """Общая логика обработки запросов из очереди."""
        while self.run_flag:
            try:
                item = self.queue_in.get(timeout=0.1)
                self._process_queue_item(item)
            except Empty:
                continue
            except ValueError:
                break

    @abstractmethod
    def _process_queue_item(self, item: Any) -> None:
        """Обработать элемент из очереди (реализуется в подклассах)."""
        pass

    @abstractmethod
    def _insert_impl(self, data: Any) -> None:
        pass

    @abstractmethod
    def _update_impl(self, data: Any) -> None:
        pass
