"""Source adapter and its process worker."""

from __future__ import annotations

import importlib
import logging
import pickle
import queue
import threading
from typing import Any

from ..base_class import EvilEyeBase
from ..mp_context import get_spawn_context
from ..plugins import PluginError, plugin_registry
from .transport import _call_factory, _serialize_process_value

_SOURCE_ITEM_MARKER = "__evileye_source_item__"


def _source_worker_entry(module_id, factory_module, factory_qualname, config, output_queue, stop_event):
    """Spawn target for source plugins implementing open/read/close."""
    logger = logging.getLogger("evileye.plugin_source")
    module = None
    try:
        factory = importlib.import_module(factory_module)
        for component in factory_qualname.split("."):
            factory = getattr(factory, component)
        module = _call_factory(factory, config)
        module.open()
        while not stop_event.is_set():
            item = module.read()
            if item is None:
                break
            serialized_item = _serialize_process_value(item, module_id, "source output")
            envelope = (_SOURCE_ITEM_MARKER, serialized_item)
            while not stop_event.is_set():
                try:
                    output_queue.put(envelope, timeout=0.1)
                    break
                except queue.Full:
                    continue
    except Exception as exc:
        logger.exception("Source plugin failed")
        try:
            output_queue.put(("__evileye_source_error__", str(exc)), timeout=0.5)
        except Exception:
            pass
        # The parent also checks the process exit code. Keep this signal even
        # when a saturated output queue prevents delivery of the error marker.
        raise SystemExit(1)
    finally:
        if module is not None:
            try:
                module.close()
            except Exception:
                logger.exception("Source plugin close failed")
        try:
            output_queue.put(("__evileye_source_done__",), timeout=0.5)
        except Exception:
            pass


class SourceModuleAdapter(EvilEyeBase):
    """Adapt ``open/read/close`` source plugins to ProcessorSource."""

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self._source_ids = []
        self._backend_execution_mode = "thread"
        self._capture_source_backend = False
        self._config: dict[str, Any] = {}
        self._subscribers: list[Any] = []
        self._output_queue = queue.Queue(maxsize=16)
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._process = None
        self._process_stop_event = None
        self._module = None
        self._backend_worker_exitcodes: list[int | None] | None = None
        self._finished = False
        self.degraded = False
        self.last_error = None
        self._thread_stop_timeout_secs = 2.0
        self._process_stop_timeout_secs = 3.0
        self._process_terminate_timeout_secs = 1.0
        self._failure_reported = False
        super().__init__()

    def _mark_degraded(self, message: str) -> None:
        message = str(message)
        self.degraded = True
        if message != self.last_error:
            self.last_error = message
            self.logger.error("Source %s degraded: %s", self.module_id, message)

    def set_params_impl(self):
        if self.is_running():
            raise PluginError(
                f"Source '{self.module_id}' cannot be reconfigured while its worker is running"
            )
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        registered = plugin_registry.get_module(self.module_id)
        capabilities = set(registered.spec.capabilities) if registered else set()
        self._capture_source_backend = "capture_source_backend" in capabilities
        managed_backend = self._capture_source_backend
        nested_config = params.get("config") or {}
        configured_mode = str(
            params.get(
                "execution_mode",
                nested_config.get(
                    "execution_mode",
                    self.registered_module.spec.default_execution_mode
                    or ("process" if managed_backend else "thread"),
                ),
            )
        ).lower()
        self._backend_execution_mode = configured_mode
        # Capture backends expose the source SPI through this control adapter,
        # while preserving their optimized shared-memory capture implementation.
        self.execution_mode = "thread" if managed_backend else configured_mode
        self._source_ids = list(
            params.get("source_ids") or nested_config.get("source_ids") or []
        )
        self._queue_size = max(1, int(params.get("queue_size", 16)))
        reserved = {"module_id", "queue_size", "ipc_mode", "config", "type", "execution_mode"}
        self._config = dict(nested_config)
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        if self._source_ids:
            self._config.setdefault("source_ids", self._source_ids)
        if managed_backend:
            self._config["execution_mode"] = configured_mode
        self._output_queue = queue.Queue(maxsize=self._queue_size)

    def get_params_impl(self):
        module = self.__dict__.get("_module")
        if self._capture_source_backend and module is not None:
            return module.get_params()
        return dict(self.params or {})

    def calc_memory_consumption(self):
        module = self.__dict__.get("_module")
        callback = getattr(module, "calc_memory_consumption", None)
        if self._capture_source_backend and callable(callback):
            callback()
            self.memory_measure_results = getattr(module, "memory_measure_results", None)
            self.memory_measure_time = getattr(module, "memory_measure_time", None)
            return
        super().calc_memory_consumption()

    def get_source_ids(self):
        return self.source_ids

    @property
    def source_ids(self):
        module = self.__dict__.get("_module")
        if module is not None and getattr(module, "source_ids", None) is not None:
            return module.source_ids
        return self._source_ids

    def __getattr__(self, name: str):
        """Expose capture source metadata and event helpers through the adapter."""
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            value = getattr(module, name)
            if value is not None:
                return value
        config = self.__dict__.get("_config", {})
        fallback = {
            "source_names": config.get("source_names", self.__dict__.get("_source_ids", [])),
            "source_address": config.get("camera", ""),
            "source_type": config.get("source"),
            "desired_fps": config.get("desired_fps"),
            "split_stream": config.get("split", False),
            "num_split": config.get("num_split"),
            "src_coords": config.get("src_coords"),
            "video_duration": None,
            "source_fps": None,
            "username": config.get("username"),
            "password": config.get("password"),
        }
        if name in fallback:
            return fallback[name]
        raise AttributeError(name)

    def _ensure_managed_source_module(self):
        if not self._capture_source_backend or self._module is not None:
            return self._module
        module = _call_factory(self.registered_module.spec.factory, self._config)
        if not all(callable(getattr(module, name, None)) for name in ("open", "read", "close")):
            raise PluginError(
                f"Capture source '{self.module_id}' must implement open(), read(), and close()"
            )
        self._module = module
        if self._subscribers and callable(getattr(module, "subscribe", None)):
            module.subscribe(*self._subscribers)
        return module

    def subscribe(self, *subscribers):
        self._subscribers = list(subscribers)
        module = self.__dict__.get("_module")
        if module is not None and callable(getattr(module, "subscribe", None)):
            module.subscribe(*subscribers)

    def get_disconnects_info(self):
        module = self.__dict__.get("_module")
        callback = getattr(module, "get_disconnects_info", None)
        return callback() if callable(callback) else []

    def get_reconnects_info(self):
        module = self.__dict__.get("_module")
        callback = getattr(module, "get_reconnects_info", None)
        return callback() if callable(callback) else []

    def init_impl(self, **kwargs):
        registered = plugin_registry.get_module(self.module_id)
        if registered is None or registered.spec.kind != "source":
            raise PluginError(f"Unknown source plugin '{self.module_id}'")
        requested_mode = (
            self._backend_execution_mode
            if self._capture_source_backend
            else self.execution_mode
        )
        if requested_mode not in registered.spec.execution_modes:
            raise PluginError(
                f"Source '{self.module_id}' does not support execution_mode='{requested_mode}'"
            )
        self.registered_module = registered
        if requested_mode == "process":
            _serialize_process_value(
                self._config, self.module_id, "source configuration"
            )
        if self._capture_source_backend:
            self._ensure_managed_source_module()
        return True

    def start(self):
        if self.is_running():
            raise PluginError(
                f"Source '{self.module_id}' cannot start while its previous worker is running"
            )
        self._finished = False
        self._failure_reported = False
        if self.execution_mode == "process":
            context = get_spawn_context()
            self._output_queue = context.Queue(maxsize=self._queue_size)
            self._process_stop_event = context.Event()
            factory = self.registered_module.spec.factory
            self._process = context.Process(
                target=_source_worker_entry,
                args=(self.module_id, factory.__module__, factory.__qualname__,
                      self._config, self._output_queue, self._process_stop_event),
                daemon=True,
                name=f"PluginSource-{self.module_id.replace('/', '-')}",
            )
            self._process.start()
            return

        self._stop_event.clear()
        if not self._capture_source_backend:
            self._module = None
        self._thread = threading.Thread(
            target=self._read_thread,
            name=f"PluginSource-{self.module_id.replace('/', '-')}",
            daemon=True,
        )
        self._thread.start()

    def _put_output(self, item):
        while not self._stop_event.is_set():
            try:
                self._output_queue.put(item, timeout=0.1)
                return True
            except queue.Full:
                continue
        self._mark_degraded("source stopped before an item could be delivered")
        return False

    def _read_thread(self):
        if self._capture_source_backend:
            self._read_capture_source_backend()
            return
        try:
            self._module = _call_factory(self.registered_module.spec.factory, self._config)
            if not all(callable(getattr(self._module, name, None)) for name in ("open", "read", "close")):
                raise PluginError(
                    f"Source '{self.module_id}' must implement open(), read(), and close()"
                )
            if self._subscribers and callable(getattr(self._module, "subscribe", None)):
                self._module.subscribe(*self._subscribers)
            self._module.open()
            while not self._stop_event.is_set():
                item = self._module.read()
                if item is None:
                    self._finished = True
                    return
                if not self._put_output(item):
                    return
        except Exception as exc:
            self._mark_degraded(f"source read failed: {exc}")
            self.logger.exception("Source plugin %s failed", self.module_id)
        finally:
            self._finished = True
            if self._module is not None:
                try:
                    self._module.close()
                except Exception as exc:
                    self._mark_degraded(f"source close failed: {exc}")
                    self.logger.exception("Source plugin %s close failed", self.module_id)

    def _read_capture_source_backend(self):
        module = self._ensure_managed_source_module()
        backend_processes = []
        try:
            module.open()
            backend_control = getattr(module, "_mp_control", None)
            backend_processes = list(getattr(backend_control, "processes", []) or [])
            while not self._stop_event.is_set():
                item = module.read()
                if item is None:
                    self._finished = True
                    return
                if not self._put_output(item):
                    return
        except Exception as exc:
            self._mark_degraded(f"capture source read failed: {exc}")
            self.logger.exception("Capture source plugin %s failed", self.module_id)
        finally:
            self._finished = True
            try:
                module.close()
            except Exception as exc:
                self._mark_degraded(f"capture source close failed: {exc}")
                self.logger.exception("Capture source plugin %s close failed", self.module_id)
            self._capture_source_worker_exitcodes(backend_processes)

    def get(self):
        # Surface non-zero exits even when there were no queued source items.
        self.get_runtime_stats()
        items = []
        q = self._output_queue
        for _ in range(64):
            try:
                item = q.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and item and item[0] == "__evileye_source_done__":
                self._finished = True
                continue
            if isinstance(item, tuple) and item and item[0] == "__evileye_source_error__":
                self._mark_degraded(f"source process failed: {item[1]}")
                self._finished = True
                continue
            if self.execution_mode == "process":
                if not (
                    isinstance(item, tuple)
                    and len(item) == 2
                    and item[0] == _SOURCE_ITEM_MARKER
                ):
                    self._mark_degraded("source process returned an invalid envelope")
                    self._finished = True
                    self.logger.error(
                        "Source plugin %s returned an invalid process envelope",
                        self.module_id,
                    )
                    continue
                try:
                    item = pickle.loads(item[1])
                except Exception as exc:
                    self._mark_degraded(f"source returned an invalid serialized item: {exc}")
                    self._finished = True
                    self.logger.error(
                        "Source plugin %s returned an invalid serialized item: %s",
                        self.module_id,
                        exc,
                    )
                    continue
            items.append(item)
        if self.execution_mode == "process" and self._process is not None and not self._process.is_alive():
            self._finished = True
            if self._process.exitcode not in (None, 0) and not self._failure_reported:
                self._mark_degraded(
                    f"source worker exited unexpectedly (exit_code={self._process.exitcode})"
                )
                self._failure_reported = True
                self.logger.error(
                    "Source plugin %s worker exited (exit_code=%s)",
                    self.module_id,
                    self._process.exitcode,
                )
        return items

    def get_runtime_stats(self) -> dict[str, Any]:
        if (
            self.execution_mode == "process"
            and self._process is not None
            and not self._process.is_alive()
            and self._process.exitcode not in (None, 0)
        ):
            self._mark_degraded(
                f"source worker exited unexpectedly (exit_code={self._process.exitcode})"
            )
            if not self._failure_reported:
                self._failure_reported = True
                self.logger.error(
                    "Source plugin %s worker exited (exit_code=%s)",
                    self.module_id,
                    self._process.exitcode,
                )
        try:
            queue_size = self._output_queue.qsize()
        except Exception:
            queue_size = None
        backend_running = None
        module = self.__dict__.get("_module")
        control = getattr(module, "_mp_control", None) if module is not None else None
        if control is not None:
            try:
                backend_running = control.is_alive()
                exitcodes = [process.exitcode for process in control.processes]
                self._backend_worker_exitcodes = exitcodes
                if any(code not in (None, 0) for code in exitcodes):
                    self._mark_degraded(f"capture backend worker exited unexpectedly: {exitcodes}")
            except Exception:
                pass
        capture_health = None
        module = self.__dict__.get("_module")
        get_capture_health = getattr(module, "get_capture_health", None)
        if callable(get_capture_health):
            try:
                capture_health = get_capture_health()
            except Exception as exc:
                self._mark_degraded(f"source health query failed: {exc}")
        backend_metrics = None
        get_metrics = getattr(control, "get_metrics", None)
        if callable(get_metrics):
            try:
                backend_metrics = get_metrics()
            except Exception as exc:
                self._mark_degraded(f"source backend metrics failed: {exc}")
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "backend_execution_mode": self._backend_execution_mode,
            "capture_health": capture_health,
            "backend_worker_metrics": backend_metrics,
            "backend_worker_running": backend_running,
            "backend_worker_exitcodes": self._backend_worker_exitcodes,
            "worker_running": self.is_running(),
            "finished": self._finished,
            "last_error": self.last_error,
            "queue_size": queue_size,
            "degraded": self.degraded,
        }

    def get_debug_info(self, debug_info: dict | None):
        if debug_info is None:
            debug_info = {}
        super().get_debug_info(debug_info)
        debug_info["plugin_runtime"] = self.get_runtime_stats()
        return debug_info

    def is_finished(self):
        return self._finished

    def is_running(self):
        if self.execution_mode == "process":
            return bool(self._process is not None and self._process.is_alive())
        return bool(self._thread is not None and self._thread.is_alive())

    def stop(self):
        self._stop_event.set()
        if self._process_stop_event is not None:
            self._process_stop_event.set()
        module = self.__dict__.get("_module")
        if self._capture_source_backend and module is not None:
            backend_control = getattr(module, "_mp_control", None)
            backend_processes = list(getattr(backend_control, "processes", []) or [])
            try:
                module.stop()
            except Exception as exc:
                self._mark_degraded(f"capture source stop failed: {exc}")
                self.logger.exception("Capture source plugin %s stop failed", self.module_id)
            self._capture_source_worker_exitcodes(backend_processes)

        thread = self._thread
        if thread is not None:
            thread.join(timeout=self._thread_stop_timeout_secs)
            if thread.is_alive():
                self._mark_degraded(
                    "source thread did not stop before timeout; "
                    f"worker_alive=true, timeout={self._thread_stop_timeout_secs}s"
                )
            else:
                self._thread = None

        process = self._process
        if process is not None:
            process.join(timeout=self._process_stop_timeout_secs)
            if process.is_alive():
                self._mark_degraded(
                    "source process did not stop before timeout; terminating worker; "
                    f"timeout={self._process_stop_timeout_secs}s"
                )
                process.terminate()
                process.join(timeout=self._process_terminate_timeout_secs)
                if process.is_alive():
                    self._mark_degraded(
                        "source process remained alive after terminate; "
                        f"worker_alive=true, exit_code={process.exitcode}"
                    )
                else:
                    self._mark_degraded(
                        f"source process required forced termination (exit_code={process.exitcode})"
                    )
            if not process.is_alive():
                self._process = None

        if not self.is_running():
            self._finished = True

    def release_impl(self):
        self.stop()
        if self.is_running():
            self._mark_degraded("source resources remain owned by a worker that did not stop")
            return
        module = self.__dict__.get("_module")
        if module is not None and self._capture_source_backend:
            try:
                self._close_managed_source_module(module)
            except Exception:
                self.logger.exception("Source plugin %s release failed", self.module_id)

    def _close_managed_source_module(self, module) -> None:
        close = getattr(module, "close", None)
        if not callable(close):
            raise PluginError("Capture source backend lost its required close() method")
        if getattr(module, "_plugin_source_opened", True) is False:
            return
        close()

    def _capture_source_worker_exitcodes(self, module) -> None:
        if module is None:
            return
        try:
            control = None
            if isinstance(module, (list, tuple)):
                processes = list(module)
            else:
                control = getattr(module, "_mp_control", None)
                processes = list(getattr(control, "processes", []) or [])
            exitcodes = [process.exitcode for process in processes]
            if not exitcodes:
                return
            self._backend_worker_exitcodes = exitcodes
            # Source.stop() intentionally terminates capture workers; normal
            # Python process termination is 0 or SIGTERM (-15).
            expected_exitcodes = {0, -15}
            unexpected = [
                code for code in exitcodes
                if code is not None and code not in expected_exitcodes
            ]
            still_running = [
                process for process in processes
                if callable(getattr(process, "is_alive", None)) and process.is_alive()
            ]
            if unexpected or still_running:
                self.degraded = True
                self.logger.error(
                    "Capture source plugin %s backend workers stopped unexpectedly "
                    "(exitcodes=%s, still_running=%s)",
                    self.module_id,
                    exitcodes,
                    len(still_running),
                )
        except Exception:
            self.logger.debug("Could not read backend worker status for %s", self.module_id)

    def reset_impl(self):
        if self._capture_source_backend:
            restart = self.is_running()
            self.stop()
            if self.is_running():
                self._mark_degraded("cannot reset capture source while its worker is still running")
                return
            module = self.__dict__.get("_module")
            if module is not None:
                try:
                    self._close_managed_source_module(module)
                except Exception:
                    self.logger.exception("Capture source plugin %s reset release failed", self.module_id)
            self._module = None
            self.is_inited = False
            self._finished = False
            self.degraded = False
            self.last_error = None
            self._failure_reported = False
            self._backend_worker_exitcodes = None
            initialized = self.init()
            if restart and initialized:
                self.start()
            return
        self.stop()
        if self.is_running():
            self._mark_degraded("cannot reset source while its worker is still running")
            return
        self.degraded = False
        self.last_error = None
        self._failure_reported = False
        self._finished = False
        while True:
            try:
                self._output_queue.get_nowait()
            except queue.Empty:
                break

    def default(self):
        self.reset_impl()
