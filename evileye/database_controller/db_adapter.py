from __future__ import annotations

from typing import Any, Optional, Dict
from ..core.base_class import EvilEyeBase
from ..core.interfaces import IDatabaseAdapter
from .database_controller_pg import DatabaseControllerPg
from .database_error_handler import DatabaseErrorHandler
from threading import Lock, Thread, current_thread
from queue import Queue, Empty
from abc import abstractmethod, ABC


class DatabaseAdapterBase(EvilEyeBase, ABC):
    def __init__(self, db_controller: DatabaseControllerPg):
        super().__init__()
        self.db_controller: DatabaseControllerPg = db_controller
        self.db_params: Dict[str, Any] = self.db_controller.get_params()
        self.cameras_params: Dict[str, Any] = self.db_controller.get_cameras_params()
        self.query_thread: Optional[Thread] = None
        self.run_flag: bool = False
        self._closing = False
        self._lifecycle_lock = Lock()
        self.stop_timeout_secs = 5.0
        self.shutdown_timeouts = 0
        self.queue_maxsize = 1024
        self.queue_in: Queue = Queue(maxsize=self.queue_maxsize)
        self.queue_failures = 0
        self.enqueue_rejections = 0
        self.terminal_write_failures = 0
        self.processed_items = 0
        self.degraded = False
        self.last_error: Optional[str] = None
        self.table_name: Optional[str] = None
        self.event_name: Optional[str] = None
        # Батчинг: размер батча и таймаут для сбора запросов (секунды)
        self.batch_size: int = 10  # По умолчанию батчинг отключен (batch_size=1 означает обработку по одному)
        self.batch_timeout: float = 0.1  # Максимальное время ожидания для формирования батча
        # Обработчик ошибок
        self.error_handler: DatabaseErrorHandler = DatabaseErrorHandler(logger=self.logger)

    def set_params_impl(self) -> None:
        self.table_name = self.params['table_name']
        queue_maxsize = int(self.params.get('queue_maxsize', self.queue_maxsize))
        if queue_maxsize < 1:
            raise ValueError('queue_maxsize must be a positive integer')
        if queue_maxsize != self.queue_maxsize:
            if not self.queue_in.empty() or self.run_flag:
                raise RuntimeError('queue_maxsize cannot change while the adapter is active')
            self.queue_maxsize = queue_maxsize
            self.queue_in = Queue(maxsize=queue_maxsize)
        # Параметры батчинга (опционально)
        self.batch_size = self.params.get('batch_size', 10)
        self.batch_timeout = self.params.get('batch_timeout', 0.1)

    def get_params_impl(self) -> Dict[str, Any]:
        params: Dict[str, Any] = dict()
        params['table_name'] = self.table_name
        params['queue_maxsize'] = self.queue_maxsize
        return params

    def init_impl(self) -> None:
        pass

    def get_event_name(self) -> Optional[str]:
        return self.event_name

    def get_table_name(self) -> Optional[str]:
        return self.table_name

    def start(self) -> None:
        with self._lifecycle_lock:
            thread = self.query_thread
            if thread is not None and thread.is_alive():
                if self.run_flag and not self._closing:
                    return
                raise RuntimeError(
                    "Cannot restart database adapter while its previous worker is still stopping"
                )
            self.run_flag = True
            self._closing = False
            if thread is None or thread.ident is not None:
                self.query_thread = Thread(
                    target=self._execute_query,
                    name=f"DatabaseAdapter-{self.event_name or self.__class__.__name__}",
                )
            self.query_thread.start()

    def stop(self) -> None:
        with self._lifecycle_lock:
            self._closing = True
            self.run_flag = False
            thread = self.query_thread
            try:
                pending = self.queue_in.qsize()
            except Exception:
                pending = "unknown"

        if thread is None or not thread.is_alive():
            if pending:
                error = RuntimeError(
                    f"database adapter has {pending} pending items but no running worker"
                )
                self._record_failure(
                    "shutdown with pending items",
                    error,
                    category="terminal_write",
                )
            return
        if thread is current_thread():
            return

        thread.join(timeout=self.stop_timeout_secs)
        if thread.is_alive():
            try:
                pending = self.queue_in.qsize()
            except Exception:
                pending = "unknown"
            self.shutdown_timeouts += 1
            self.degraded = True
            self.last_error = (
                "database adapter shutdown timed out; "
                f"worker_alive=true, pending_items={pending}"
            )
            self.logger.error(self.last_error)

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
                exc = ConnectionError(f"Database adapter '{self.event_name}' is disconnected")
                self._record_failure('insert', exc, category='enqueue')
                raise exc
        # Serialize acceptance with stop(): work accepted before shutdown is drained,
        # and work arriving after shutdown is explicitly rejected.
        with self._lifecycle_lock:
            if self._closing:
                exc = RuntimeError(
                    "Database adapter worker is not running because the adapter is stopping"
                )
                self._record_failure('insert', exc, category='enqueue')
                raise exc
            self._insert_impl(data)

    def update(self, data: Any) -> None:
        # Проверяем, что БД подключена перед выполнением операций (только для БД адаптеров)
        # JSON адаптеры не имеют db_controller с методом is_connected(), поэтому проверяем наличие метода
        if self.db_controller and hasattr(self.db_controller, 'is_connected'):
            if not self.db_controller.is_connected():
                exc = ConnectionError(f"Database adapter '{self.event_name}' is disconnected")
                self._record_failure('update', exc, category='enqueue')
                raise exc
        # Keep updates under the same acceptance boundary as inserts.
        with self._lifecycle_lock:
            if self._closing:
                exc = RuntimeError(
                    "Database adapter worker is not running because the adapter is stopping"
                )
                self._record_failure('update', exc, category='enqueue')
                raise exc
            self._update_impl(data)

    def get_db_params(self) -> Dict[str, Any]:
        return self.db_params

    def get_cameras_params(self) -> Dict[str, Any]:
        return self.cameras_params

    def _record_failure(
        self,
        operation: str,
        error: Exception,
        *,
        category: str = "enqueue",
    ) -> None:
        self.queue_failures += 1
        if category == "enqueue":
            self.enqueue_rejections += 1
        elif category == "terminal_write":
            self.terminal_write_failures += 1
        else:
            raise ValueError(f"Unknown database adapter failure category: {category}")
        self.degraded = True
        self.last_error = f"{operation}: {type(error).__name__}: {error}"
        self.logger.error(
            "Database adapter '%s' %s failed: %s",
            self.event_name,
            operation,
            error,
            exc_info=(type(error), error, error.__traceback__),
        )

    def get_runtime_stats(self) -> dict[str, Any]:
        try:
            pending = self.queue_in.qsize()
        except Exception:
            pending = None
        return {
            "event_name": self.event_name,
            "queue_size": pending,
            "queue_maxsize": self.queue_maxsize,
            "queue_failures": self.queue_failures,
            "enqueue_rejections": self.enqueue_rejections,
            "terminal_write_failures": self.terminal_write_failures,
            "processed_items": self.processed_items,
            "worker_alive": bool(self.query_thread and self.query_thread.is_alive()),
            "closing": self._closing,
            "shutdown_timeouts": self.shutdown_timeouts,
            "degraded": self.degraded,
            "last_error": self.last_error,
        }

    def _execute_query(self) -> None:
        """Retry transient writes and report every item that cannot be saved."""
        while self.run_flag or not self.queue_in.empty():
            try:
                item = self.queue_in.get(timeout=0.1)
            except Empty:
                continue
            _, error = self.error_handler.execute_with_retry(
                lambda: self._process_queue_item(item),
                max_retries=3,
                initial_delay=0.1,
                max_delay=0.5,
            )
            if error is not None:
                self._record_failure('queued write', error, category='terminal_write')
            else:
                self.processed_items += 1

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
