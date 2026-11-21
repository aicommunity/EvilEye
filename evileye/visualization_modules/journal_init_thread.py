"""
Поток для инициализации DatabaseJournalWindow с обновлением прогресса
"""

try:
    from PyQt6.QtCore import QThread, pyqtSignal

    pyqt_version = 6
except ImportError:
    from PyQt5.QtCore import QThread, pyqtSignal

    pyqt_version = 5

from ..database_controller import database_controller_pg
from ..core.logger import get_module_logger
import atexit
import logging
import threading


class JournalInitThread(QThread):
    """Поток для инициализации DatabaseJournalWindow в фоновом режиме"""

    _instances: set["JournalInitThread"] = set()
    _instances_lock = threading.Lock()

    # Сигналы для обновления прогресса и завершения
    progress_updated = pyqtSignal(str)  # stage_text
    initialization_complete = pyqtSignal(object)  # db_controller
    initialization_failed = pyqtSignal(str)  # error_message

    def __init__(self, params, database_params, logger_name: str | None = None,
                 parent_logger: logging.Logger | None = None):
        super().__init__()
        self.params = params
        self.database_params = database_params
        base_name = "evileye.journal_init_thread"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.db_controller = None
        with self._instances_lock:
            self._instances.add(self)

    @classmethod
    def shutdown_all(cls, timeout_ms: int = 7000) -> None:
        """Request cancellation and wait for active journal workers to finish."""
        with cls._instances_lock:
            threads = list(cls._instances)
        active = [thread for thread in threads if thread.isRunning()]
        for thread in active:
            thread.requestInterruption()
        for thread in active:
            if not thread.wait(timeout_ms):
                thread.logger.error(
                    "Journal initialization thread did not stop within %sms",
                    timeout_ms,
                )
        with cls._instances_lock:
            finished = [thread for thread in cls._instances if not thread.isRunning()]
            cls._instances.difference_update(finished)

    def run(self):
        """Выполнить инициализацию БД контроллера"""
        import platform
        import sys

        try:
            if self.isInterruptionRequested():
                return
            self.progress_updated.emit("Initializing database controller...")
            self.logger.info("Creating DatabaseControllerPg...")

            # Создание контроллера БД
            try:
                self.db_controller = database_controller_pg.DatabaseControllerPg(self.params,
                                                                                 controller_type='Receiver')
                self.logger.info("DatabaseControllerPg instance created")
                if self.isInterruptionRequested():
                    return
            except Exception as e:
                error_msg = f"Failed to create DatabaseControllerPg: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                self.initialization_failed.emit(error_msg)
                return

            # Установка параметров БД
            try:
                self.db_controller.set_params(**self.database_params['database'])
                self.logger.info("DatabaseControllerPg params set")
                if self.isInterruptionRequested():
                    return
            except Exception as e:
                error_msg = f"Failed to set database parameters: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                self.initialization_failed.emit(error_msg)
                return

            # Инициализация БД контроллера
            self.progress_updated.emit("Connecting to database...")
            self.logger.info("About to call db_controller.init()...")
            try:
                self.db_controller.init()
                self.logger.info("db_controller.init() completed")
                if self.isInterruptionRequested():
                    return
            except Exception as e:
                error_msg = f"Database initialization failed: {str(e)}"
                self.logger.warning(error_msg, exc_info=True)
                # Продолжаем попытку подключения даже если init() не удался
                self.logger.info("Continuing with connection attempt despite init() failure...")

            # Подключение к БД
            self.progress_updated.emit("Establishing database connection...")
            self.logger.info("About to connect to database...")
            try:
                self.db_controller.connect()
                self.logger.info("Database connected successfully")
                if self.isInterruptionRequested():
                    return

                # Отправляем сигнал об успешном завершении
                self.initialization_complete.emit(self.db_controller)

            except Exception as e:
                # Детальное логирование ошибки подключения
                db_params = self.database_params.get('database', {})
                error_context = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'host': db_params.get('host_name', 'unknown'),
                    'port': db_params.get('port', 'unknown'),
                    'database': db_params.get('database_name', 'unknown'),
                    'user': db_params.get('user_name', 'unknown'),
                    'platform': f"{platform.system()} {platform.release()}",
                    'python_version': sys.version.split()[0]
                }

                error_msg = f"Journal initialization error: {str(e)}"
                self.logger.error(error_msg, exc_info=True)
                self.logger.debug(f"Database connection context: {error_context}")

                # Убеждаемся, что контроллер БД в безопасном состоянии
                if self.db_controller:
                    self.db_controller.conn_pool = None

                self.initialization_failed.emit(error_msg)

        except Exception as e:
            # Перехватываем любые неожиданные ошибки
            error_msg = f"Unexpected error during journal initialization: {str(e)}"
            self.logger.error(error_msg, exc_info=True)

            # Убеждаемся, что контроллер БД в безопасном состоянии
            if self.db_controller:
                self.db_controller.conn_pool = None

            if not self.isInterruptionRequested():
                self.initialization_failed.emit(error_msg)
        finally:
            if self.isInterruptionRequested() and self.db_controller is not None:
                try:
                    self.db_controller.disconnect()
                except Exception:
                    pass
            # Keep a strong reference until shutdown_all() observes that the
            # native QThread has fully stopped. `run()`'s finally block runs
            # just before QThread transitions out of isRunning(), so removing
            # self here can destroy the wrapper while its native thread exits.


atexit.register(JournalInitThread.shutdown_all)
