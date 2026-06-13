import threading
from typing import Dict, Optional
from .mp_control import MpControl
from .logger import get_module_logger
from .runtime_context import get_runtime_context, get_or_create_runtime_service


class ProcessManager:
    """Centralized registry for all MpControl instances in the pipeline

    Provides a single place to start, stop, and query all multiprocessing
    pools used by the system (detection, tracking, attributes, web server)
    """

    def __init__(self):
        self.logger = get_module_logger("process_manager")
        self._lock = threading.Lock()
        self._pools: Dict[str, MpControl] = {}

    def register(self, name: str, pool: MpControl) -> None:
        with self._lock:
            if name in self._pools:
                self.logger.warning(f"Pool '{name}' already registered, replacing")
            self._pools[name] = pool
            self.logger.info(f"Registered pool '{name}'")

    def unregister(self, name: str) -> Optional[MpControl]:
        with self._lock:
            pool = self._pools.pop(name, None)
            if pool:
                self.logger.info(f"Unregistered pool '{name}'")
            return pool

    def get(self, name: str) -> Optional[MpControl]:
        with self._lock:
            return self._pools.get(name)

    def start_all(self) -> None:
        with self._lock:
            for name, pool in self._pools.items():
                self.logger.info(f"Starting pool '{name}'")
                pool.start()

    def stop_all(self, timeout: float = 10.0) -> None:
        with self._lock:
            names = list(self._pools.keys())

        for name in names:
            pool = self._pools.get(name)
            if pool is not None:
                self.logger.info(f"Stopping pool '{name}'")
                try:
                    pool.stop(timeout=timeout)
                except Exception as e:
                    self.logger.error(f"Error stopping pool '{name}': {e}")

    def status(self) -> Dict[str, dict]:
        with self._lock:
            result = {}
            for name, pool in self._pools.items():
                result[name] = {
                    "alive": pool.is_alive(),
                    "workers": pool.worker_count(),
                }
            return result

    def shutdown(self) -> None:
        """Stop all pools and clear the registry"""
        self.stop_all()
        with self._lock:
            self._pools.clear()
        self.logger.info("ProcessManager shutdown complete")


def get_process_manager() -> ProcessManager:
    ctx = get_runtime_context()
    if ctx.process_manager is not None:
        return ctx.process_manager
    manager: Optional[ProcessManager] = get_or_create_runtime_service("process_manager", ProcessManager)
    return manager
