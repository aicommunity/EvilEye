"""Runtime adapter for user-authored item processors."""

from __future__ import annotations

import inspect
import importlib
import queue
import threading
import logging
from typing import Any

from .base_class import EvilEyeBase
from .mp_worker import MpWorker
from .plugins import PluginError, plugin_registry
from .mp_context import get_spawn_context


def _call_factory(factory, config: dict[str, Any]):
    """Call a plugin factory with its config when its signature accepts it."""
    try:
        signature = inspect.signature(factory)
    except (TypeError, ValueError):
        return factory(config)
    positional = [
        p for p in signature.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if positional:
        return factory(config)
    if "config" in signature.parameters:
        return factory(config=config)
    return factory()


def _create_state(module: Any, config: dict[str, Any]) -> Any:
    create_state = getattr(module, "create_state", None)
    if not callable(create_state):
        return None
    try:
        signature = inspect.signature(create_state)
    except (TypeError, ValueError):
        return create_state(config)
    positional = [
        p for p in signature.parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if positional:
        return create_state(config)
    if "config" in signature.parameters:
        return create_state(config=config)
    return create_state()


def _close_item_resources(module: Any, state: Any, logger, module_id: str) -> None:
    """Close optional per-worker module/state resources without double-closing."""
    seen: set[int] = set()
    for target in (state, module):
        if target is None or id(target) in seen:
            continue
        seen.add(id(target))
        close = getattr(target, "close", None)
        if not callable(close):
            close = getattr(target, "release", None)
        if not callable(close):
            continue
        try:
            close()
        except Exception:
            if logger:
                logger.exception("Plugin module %s failed to close worker resources", module_id)


class ItemModuleWorker(MpWorker):
    """Spawn-safe bridge that recreates a plugin module inside the child."""

    def apply_spawn_state(self, state: dict[str, Any]) -> None:
        self.module_id = state["module_id"]
        self.config = state.get("config") or {}
        self.factory_module = state["factory_module"]
        self.factory_qualname = state["factory_qualname"]
        self.module = None
        self.module_state = None
        self.drop_oldest_on_full = False

    def init_worker(self) -> None:
        try:
            factory = importlib.import_module(self.factory_module)
            for component in self.factory_qualname.split("."):
                factory = getattr(factory, component)
            self.module = _call_factory(factory, self.config)
            if not callable(getattr(self.module, "process_item", None)):
                raise PluginError(
                    f"Module '{self.module_id}' must implement process_item(item, state)"
                )
            self.module_state = _create_state(self.module, self.config)
        except Exception:
            _close_item_resources(self.module, self.module_state, self.logger, self.module_id)
            self.module = None
            self.module_state = None
            raise

    def worker_impl(self, data):
        try:
            result = self.module.process_item(data, self.module_state)
        except Exception as exc:
            if self.logger:
                self.logger.exception("Plugin module %s failed while processing item", self.module_id)
            self._stop_event.set()
            return ("__evileye_plugin_runtime__", "error", str(exc))
        if result is None:
            return None
        return ("__evileye_plugin_runtime__", "output", result)

    def get_spawn_state(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "config": self.config,
            "factory_module": self.factory_module,
            "factory_qualname": self.factory_qualname,
        }

    def cleanup(self) -> None:
        _close_item_resources(self.module, self.module_state, self.logger, self.module_id)
        self.module = None
        self.module_state = None


class ItemModuleAdapter(EvilEyeBase):
    """Expose ``process_item(item, state)`` plugins as pipeline processors.

    The adapter has the same ``put/get`` lifecycle expected by ProcessorStep
    and chooses an in-process worker thread or the existing MpControl/spawn
    worker from configuration.
    """

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids = None
        capabilities = set(registered_module.spec.capabilities or ())
        factory = registered_module.spec.factory
        self._config: dict[str, Any] = {}
        self._input_queue: queue.Queue = queue.Queue(maxsize=8)
        self._output_queue: queue.Queue = queue.Queue(maxsize=8)
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._module = None
        self._state = None
        self._mp_control = None
        self.degraded = False
        self._failure_reported = False
        super().__init__()
        self.accepts_frame_handle = (
            "accepts_frame_handle" in capabilities
            or bool(getattr(factory, "accepts_frame_handle", False))
        )
        self.emits_dto_type = getattr(factory, "emits_dto_type", None)
        for capability in capabilities:
            if capability.startswith("emits_dto_type:"):
                self.emits_dto_type = capability.split(":", 1)[1]
                break
        self.requires_materialized_frame = (
            "requires_materialized_frame" in capabilities
            or bool(getattr(factory, "requires_materialized_frame", not self.accepts_frame_handle))
        )

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        self.execution_mode = str(params.get("execution_mode", "thread")).lower()
        self.source_ids = params.get("source_ids")
        if self.source_ids is not None:
            self.source_ids = [int(item) for item in self.source_ids]
        self._queue_size = max(1, int(params.get("queue_size", 8)))
        self._config = dict(params.get("config") or {})
        reserved = {"type", "module_id", "execution_mode", "source_ids", "queue_size", "ipc_mode"}
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        self._input_queue = queue.Queue(maxsize=self._queue_size)
        self._output_queue = queue.Queue(maxsize=self._queue_size)

    def get_params_impl(self):
        return dict(self.params or {})

    def get_source_ids(self):
        return self.source_ids

    def init_impl(self, **kwargs):
        registered = plugin_registry.get_module(self.module_id)
        if registered is None:
            raise PluginError(f"Unknown plugin module '{self.module_id}'")
        if registered.spec.kind != "processor_item":
            raise PluginError(
                f"Module '{self.module_id}' has kind '{registered.spec.kind}', "
                "expected 'processor_item' for process_item(item, state)"
            )
        if self.execution_mode not in registered.spec.execution_modes:
            raise PluginError(
                f"Module '{self.module_id}' does not support execution_mode="
                f"'{self.execution_mode}'"
            )
        self.registered_module = registered
        return True

    def start(self):
        self._stop_event.clear()
        self._failure_reported = False
        if self.execution_mode == "process":
            from .mp_control import MpControl

            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Plugin-{self.module_id.replace('/', '-')}",
                restart_on_exit=False,
            )
            worker = self._mp_control.add_worker(ItemModuleWorker)
            worker.module_id = self.module_id
            worker.config = self._config
            worker.factory_module = self.registered_module.spec.factory.__module__
            worker.factory_qualname = self.registered_module.spec.factory.__qualname__
            worker.module = None
            worker.module_state = None
            worker.drop_oldest_on_full = False
            self._mp_control.start()
            return

        self._module = None
        self._state = None
        self._thread = threading.Thread(
            target=self._run_thread,
            name=f"Plugin-{self.module_id.replace('/', '-')}",
            daemon=True,
        )
        self._thread.start()

    def _run_thread(self):
        try:
            try:
                self._module = _call_factory(
                    self.registered_module.spec.factory, self._config
                )
                if not callable(getattr(self._module, "process_item", None)):
                    raise PluginError(
                        f"Module '{self.module_id}' must implement process_item(item, state)"
                    )
                self._state = _create_state(self._module, self._config)
            except Exception:
                self.degraded = True
                self.logger.exception("Plugin module %s failed during worker initialization", self.module_id)
                return

            while not self._stop_event.is_set():
                try:
                    item = self._input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                if item is None:
                    break
                try:
                    result = self._module.process_item(item, self._state)
                    if result is not None:
                        while not self._stop_event.is_set():
                            try:
                                self._output_queue.put(result, timeout=0.1)
                                break
                            except queue.Full:
                                continue
                except Exception:
                    self.degraded = True
                    self.logger.exception("Plugin module %s failed while processing item", self.module_id)
                    break
        finally:
            _close_item_resources(self._module, self._state, self.logger, self.module_id)
            self._module = None
            self._state = None

    def put(self, item):
        try:
            if self._mp_control is not None:
                self._mp_control.put(item, block=False)
            else:
                self._input_queue.put_nowait(item)
        except queue.Full:
            self.degraded = True
            self.logger.error("Plugin module %s input queue is full", self.module_id)
            raise RuntimeError(f"Plugin module '{self.module_id}' input queue is full")

    def get(self):
        self._check_process_health()
        try:
            if self._mp_control is not None:
                result = self._mp_control.get_nowait()
                if (
                    isinstance(result, tuple)
                    and len(result) == 3
                    and result[0] == "__evileye_plugin_runtime__"
                ):
                    if result[1] == "error":
                        self.degraded = True
                        self.logger.error(
                            "Plugin module %s failed in worker: %s", self.module_id, result[2]
                        )
                        return None
                    return result[2]
                return result
            return self._output_queue.get_nowait()
        except queue.Empty:
            self._check_process_health()
            return None
        except Exception as exc:
            if exc.__class__.__name__ == "Empty":
                self._check_process_health()
                return None
            raise

    def _check_process_health(self):
        if self._mp_control is None or self._stop_event.is_set() or self._failure_reported:
            return
        exited = [
            process for process in self._mp_control.processes
            if process.exitcode is not None
        ]
        if exited:
            self.degraded = True
            self._failure_reported = True
            self.logger.error(
                "Plugin module %s worker exited unexpectedly (exit_code=%s)",
                self.module_id,
                exited[0].exitcode,
            )

    def get_runtime_stats(self) -> dict[str, Any]:
        self._check_process_health()
        worker_running = bool(self._thread is not None and self._thread.is_alive())
        if self._mp_control is not None:
            worker_running = any(p.is_alive() for p in self._mp_control.processes)
        try:
            input_queue_size = self._input_queue.qsize() if self.execution_mode == "thread" else None
            output_queue_size = self._output_queue.qsize() if self.execution_mode == "thread" else None
        except Exception:
            input_queue_size = output_queue_size = None
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "worker_running": worker_running,
            "input_queue_size": input_queue_size,
            "output_queue_size": output_queue_size,
            "degraded": self.degraded,
        }

    def get_debug_info(self, debug_info: dict | None):
        if debug_info is None:
            debug_info = {}
        super().get_debug_info(debug_info)
        debug_info["plugin_runtime"] = self.get_runtime_stats()
        return debug_info

    def stop(self):
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        self._stop_event.set()
        try:
            self._input_queue.put_nowait(None)
        except queue.Full:
            pass
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def release_impl(self):
        self.stop()

    def reset_impl(self):
        self.stop()
        self.degraded = False
        self._failure_reported = False
        while True:
            try:
                self._input_queue.get_nowait()
            except queue.Empty:
                break
        while True:
            try:
                self._output_queue.get_nowait()
            except queue.Empty:
                break

    def default(self):
        self.reset_impl()


def _source_worker_entry(factory_module, factory_qualname, config, output_queue, stop_event):
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
            while not stop_event.is_set():
                try:
                    output_queue.put(item, timeout=0.1)
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
        self._legacy_source_protocol = False
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
        self._failure_reported = False
        super().__init__()

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        registered = plugin_registry.get_module(self.module_id)
        self._legacy_source_protocol = bool(
            registered and "legacy_source_protocol" in registered.spec.capabilities
        )
        nested_config = params.get("config") or {}
        configured_mode = str(
            params.get(
                "execution_mode",
                nested_config.get(
                    "execution_mode",
                    "process" if self._legacy_source_protocol else "thread",
                ),
            )
        ).lower()
        self._backend_execution_mode = configured_mode
        # Legacy capture sources keep their optimized capture backend (including
        # shared-memory process capture), while the SPI adapter itself runs in
        # the host process and exposes frames through the common source API.
        self.execution_mode = "thread" if self._legacy_source_protocol else configured_mode
        self._source_ids = list(
            params.get("source_ids") or nested_config.get("source_ids") or []
        )
        self._queue_size = max(1, int(params.get("queue_size", 16)))
        reserved = {"module_id", "queue_size", "ipc_mode", "config"}
        if not self._legacy_source_protocol:
            reserved.update({"type", "execution_mode", "source_ids"})
        self._config = dict(nested_config)
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        if self._legacy_source_protocol:
            self._config["execution_mode"] = configured_mode
            if self._source_ids:
                self._config.setdefault("source_ids", self._source_ids)
        self._output_queue = queue.Queue(maxsize=self._queue_size)

    def get_params_impl(self):
        module = self.__dict__.get("_module")
        if self._legacy_source_protocol and module is not None:
            return module.get_params()
        return dict(self.params or {})

    def calc_memory_consumption(self):
        module = self.__dict__.get("_module")
        callback = getattr(module, "calc_memory_consumption", None)
        if self._legacy_source_protocol and callable(callback):
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
        """Expose legacy source metadata and event helpers through the adapter."""
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
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

    def _ensure_legacy_source(self):
        if not self._legacy_source_protocol or self._module is not None:
            return self._module
        module = _call_factory(self.registered_module.spec.factory, {})
        if not callable(getattr(module, "set_params", None)):
            raise PluginError(
                f"Legacy source '{self.module_id}' must implement set_params()"
            )
        module.set_params(**self._config)
        if callable(getattr(module, "set_id", None)):
            module.set_id(self.id)
        if self._subscribers and callable(getattr(module, "subscribe", None)):
            module.subscribe(*self._subscribers)
        self._module = module
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
        requested_mode = self._backend_execution_mode if self._legacy_source_protocol else self.execution_mode
        if requested_mode not in registered.spec.execution_modes:
            raise PluginError(
                f"Source '{self.module_id}' does not support execution_mode='{requested_mode}'"
            )
        self.registered_module = registered
        if self._legacy_source_protocol:
            module = self._ensure_legacy_source()
            try:
                initialized = module.init()
            except Exception:
                self.degraded = True
                self.logger.exception("Legacy source plugin %s initialization failed", self.module_id)
                return False
            if not initialized:
                self.degraded = True
            return bool(initialized)
        return True

    def start(self):
        self._finished = False
        self._failure_reported = False
        if self.execution_mode == "process":
            context = get_spawn_context()
            self._output_queue = context.Queue(maxsize=self._queue_size)
            self._process_stop_event = context.Event()
            factory = self.registered_module.spec.factory
            self._process = context.Process(
                target=_source_worker_entry,
                args=(factory.__module__, factory.__qualname__, self._config,
                      self._output_queue, self._process_stop_event),
                daemon=True,
                name=f"PluginSource-{self.module_id.replace('/', '-')}",
            )
            self._process.start()
            return

        self._stop_event.clear()
        if not self._legacy_source_protocol:
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
        self.degraded = True
        self.logger.error("Source %s stopped before item delivery", self.module_id)
        return False

    def _read_thread(self):
        if self._legacy_source_protocol:
            self._read_legacy_source()
            return
        try:
            self._module = _call_factory(self.registered_module.spec.factory, self._config)
            if not all(callable(getattr(self._module, name, None)) for name in ("open", "read", "close")):
                raise PluginError(
                    f"Source '{self.module_id}' must implement open(), read(), and close()"
                )
            self._module.open()
            while not self._stop_event.is_set():
                item = self._module.read()
                if item is None:
                    self._finished = True
                    return
                if not self._put_output(item):
                    return
        except Exception:
            self.degraded = True
            self.logger.exception("Source plugin %s failed", self.module_id)
        finally:
            self._finished = True
            if self._module is not None:
                try:
                    self._module.close()
                except Exception:
                    self.logger.exception("Source plugin %s close failed", self.module_id)

    def _read_legacy_source(self):
        module = None
        try:
            module = self._ensure_legacy_source()
            module.start()
            while not self._stop_event.is_set():
                items = module.get()
                if items:
                    if not isinstance(items, (list, tuple)):
                        items = [items]
                    for item in items:
                        if not self._put_output(item):
                            return
                    continue
                if callable(getattr(module, "is_finished", None)) and module.is_finished():
                    self._finished = True
                    return
                self._stop_event.wait(0.01)
        except Exception:
            self.degraded = True
            self.logger.exception("Legacy source plugin %s failed", self.module_id)
        finally:
            self._finished = True
            if module is not None:
                backend_control = getattr(module, "_mp_control", None)
                backend_processes = list(getattr(backend_control, "processes", []) or [])
                try:
                    module.stop()
                except Exception:
                    self.logger.exception("Legacy source plugin %s stop failed", self.module_id)
                self._capture_legacy_worker_exitcodes(backend_processes)

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
                self.degraded = True
                self.logger.error("Source plugin %s failed in process: %s", self.module_id, item[1])
                self._finished = True
                continue
            items.append(item)
        if self.execution_mode == "process" and self._process is not None and not self._process.is_alive():
            self._finished = True
            if self._process.exitcode not in (None, 0) and not self._failure_reported:
                self.degraded = True
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
            self.degraded = True
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
                    self.degraded = True
            except Exception:
                pass
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "backend_execution_mode": self._backend_execution_mode,
            "backend_worker_running": backend_running,
            "backend_worker_exitcodes": self._backend_worker_exitcodes,
            "worker_running": self.is_running(),
            "finished": self._finished,
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
        thread_alive = self._thread is not None and self._thread.is_alive()
        if thread_alive:
            self._thread.join(timeout=5.0 if self._legacy_source_protocol else 2.0)
        if self._legacy_source_protocol and module is not None and (
            not thread_alive or (self._thread is not None and self._thread.is_alive())
        ):
            backend_control = getattr(module, "_mp_control", None)
            backend_processes = list(getattr(backend_control, "processes", []) or [])
            callback = getattr(module, "stop", None)
            if callable(callback):
                try:
                    callback()
                except Exception:
                    self.logger.exception("Legacy source plugin %s stop failed", self.module_id)
            self._capture_legacy_worker_exitcodes(backend_processes)
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
        self._thread = None
        if self._process is not None:
            self._process.join(timeout=3.0)
            if self._process.is_alive():
                self._process.terminate()
                self._process.join(timeout=1.0)
            self._process = None
        self._finished = True

    def release_impl(self):
        self.stop()
        module = self.__dict__.get("_module")
        if self._legacy_source_protocol and module is not None:
            try:
                self._release_legacy_module(module)
            except Exception:
                self.logger.exception("Legacy source plugin %s release failed", self.module_id)

    @staticmethod
    def _release_legacy_module(module) -> None:
        release = getattr(module, "release", None)
        if callable(release):
            try:
                release()
            finally:
                # Some legacy sources expose a resource-only release() method
                # instead of EvilEyeBase.release(), which also clears this flag.
                if hasattr(module, "is_inited"):
                    module.is_inited = False
            return
        release_impl = getattr(module, "release_impl", None)
        if callable(release_impl):
            release_impl()
        if hasattr(module, "is_inited"):
            module.is_inited = False

    def _capture_legacy_worker_exitcodes(self, module) -> None:
        if module is None:
            return
        try:
            if isinstance(module, (list, tuple)):
                processes = module
            else:
                control = getattr(module, "_mp_control", None)
                processes = list(getattr(control, "processes", []) or [])
            exitcodes = [process.exitcode for process in processes]
            if not exitcodes:
                return
            self._backend_worker_exitcodes = exitcodes
            if any(code not in (None, 0) for code in exitcodes):
                self.degraded = True
                self.logger.error(
                    "Legacy source plugin %s backend worker exited with codes %s",
                    self.module_id,
                    exitcodes,
                )
        except Exception:
            self.logger.debug("Could not read backend worker status for %s", self.module_id)

    def reset_impl(self):
        if self._legacy_source_protocol:
            restart = self.is_running()
            self.stop()
            module = self.__dict__.get("_module")
            if module is not None:
                try:
                    self._release_legacy_module(module)
                except Exception:
                    self.logger.exception("Legacy source plugin %s reset release failed", self.module_id)
            self._module = None
            self.is_inited = False
            self._finished = False
            self.degraded = False
            self._failure_reported = False
            self._backend_worker_exitcodes = None
            initialized = self.init()
            if restart and initialized:
                self.start()
            return
        self.stop()
        self.degraded = False
        self._failure_reported = False
        self._finished = False
        while True:
            try:
                self._output_queue.get_nowait()
            except queue.Empty:
                break

    def default(self):
        self.reset_impl()
