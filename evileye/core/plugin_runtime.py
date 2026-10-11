"""Runtime adapter for user-authored item processors."""

from __future__ import annotations

import importlib
import inspect
import logging
import pickle
import queue
import threading
import time
from typing import Any, Mapping

from .base_class import EvilEyeBase
from .mp_worker import MpWorker
from .plugins import ModuleRuntimeContext, PluginError, plugin_registry
from .contracts import EventUpdate
from .mp_context import get_spawn_context


_PROCESS_INPUT_MARKER = "__evileye_plugin_input__"
_PROCESS_OUTPUT_MARKER = "__evileye_plugin_runtime__"
_SOURCE_ITEM_MARKER = "__evileye_source_item__"


def _is_frame_work_item(item: Any) -> bool:
    """Frame work can shed stale queued frames; other payloads reject overflow."""
    from .frame import Frame

    if isinstance(item, Frame):
        return True
    return (
        isinstance(item, (tuple, list))
        and len(item) == 2
        and isinstance(item[1], Frame)
    )


def _serialize_process_value(value: Any, module_id: str, label: str) -> bytes:
    try:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    except Exception as exc:
        raise PluginError(
            f"Module '{module_id}' {label} must be serializable for process "
            f"execution: {exc}"
        ) from exc


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


def _create_state(
    module: Any,
    config: dict[str, Any],
    context: ModuleRuntimeContext | None = None,
) -> Any:
    create_state = getattr(module, "create_state", None)
    if not callable(create_state):
        return None
    try:
        signature = inspect.signature(create_state)
    except (TypeError, ValueError):
        return create_state(config)
    parameters = signature.parameters
    positional = [
        p for p in parameters.values()
        if p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)
    ]
    if len(positional) >= 2:
        return create_state(config, context)
    if "context" in parameters:
        if positional:
            return create_state(config, context=context)
        kwargs = {"context": context}
        if "config" in parameters:
            kwargs["config"] = config
        return create_state(**kwargs)
    if positional:
        return create_state(config)
    if "config" in parameters:
        return create_state(config=config)
    return create_state()


def _normalize_model_class_mapping(mapping: Any, module_id: str) -> dict[str, int] | None:
    if mapping is None:
        return None
    if not isinstance(mapping, Mapping):
        raise PluginError(
            f"Module '{module_id}' class mapping metadata must be a mapping"
        )
    normalized: dict[str, int] = {}
    for name, class_id in mapping.items():
        if not isinstance(name, str) or not name.strip():
            raise PluginError(
                f"Module '{module_id}' class mapping keys must be non-empty strings"
            )
        if not isinstance(class_id, int) or isinstance(class_id, bool) or class_id < 0:
            raise PluginError(
                f"Module '{module_id}' class mapping values must be non-negative integers"
            )
        normalized[name] = class_id
    return normalized


def _get_model_class_mapping(module: Any, module_id: str) -> dict[str, int] | None:
    provider = getattr(module, "get_model_class_mapping", None)
    if not callable(provider):
        return None
    mapping = provider()
    if mapping is None:
        return None
    try:
        return _normalize_model_class_mapping(mapping, module_id)
    except PluginError as exc:
        raise PluginError(
            f"Module '{module_id}' get_model_class_mapping() is invalid: {exc}"
        ) from exc


def _validate_model_class_mapping_capability(
    module: Any, module_id: str, declared: bool
) -> None:
    provider_exists = callable(getattr(module, "get_model_class_mapping", None))
    if declared and not provider_exists:
        raise PluginError(
            f"Module '{module_id}' declares model_class_mapping but does not "
            "implement get_model_class_mapping()"
        )
    if provider_exists and not declared:
        raise PluginError(
            f"Module '{module_id}' implements get_model_class_mapping() but "
            "does not declare the model_class_mapping capability"
        )


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
        self.runtime_context = state["runtime_context"]
        self.factory_module = state["factory_module"]
        self.factory_qualname = state["factory_qualname"]
        self.module = None
        self.module_state = None
        self.drop_oldest_on_full = False
        self._last_model_class_mapping = None
        self.reports_model_class_mapping = bool(
            state.get("reports_model_class_mapping", False)
        )

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
            _validate_model_class_mapping_capability(
                self.module, self.module_id, self.reports_model_class_mapping
            )
            self.module_state = _create_state(
                self.module, self.config, self.runtime_context
            )
            self._publish_model_class_mapping()
        except Exception as exc:
            try:
                self.output_queue.put(
                    (_PROCESS_OUTPUT_MARKER, "error", f"Worker initialization failed: {exc}"),
                    timeout=1.0,
                )
            except Exception:
                if self.logger:
                    self.logger.exception(
                        "Plugin module %s could not report worker initialization failure",
                        self.module_id,
                    )
            _close_item_resources(self.module, self.module_state, self.logger, self.module_id)
            self.module = None
            self.module_state = None
            raise

    def _publish_model_class_mapping(self) -> None:
        mapping = _get_model_class_mapping(self.module, self.module_id)
        if not mapping or mapping == self._last_model_class_mapping:
            return
        payload = _serialize_process_value(
            mapping, self.module_id, "model class mapping"
        )
        while not self._stop_event.is_set():
            try:
                self.output_queue.put(
                    (_PROCESS_OUTPUT_MARKER, "metadata", payload), timeout=0.1
                )
                self._last_model_class_mapping = mapping
                return
            except queue.Full:
                continue

    def worker_impl(self, data):
        if not (
            isinstance(data, tuple)
            and len(data) == 2
            and data[0] == _PROCESS_INPUT_MARKER
        ):
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", "invalid serialized input envelope")
        try:
            item = pickle.loads(data[1])
            result = self.module.process_item(item, self.module_state)
            self._publish_model_class_mapping()
        except Exception as exc:
            if self.logger:
                self.logger.exception("Plugin module %s failed while processing item", self.module_id)
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", str(exc))
        if result is None:
            return None
        try:
            serialized_result = _serialize_process_value(
                result, self.module_id, "process_item result"
            )
        except PluginError as exc:
            if self.logger:
                self.logger.error("%s", exc)
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", str(exc))
        return (_PROCESS_OUTPUT_MARKER, "output", serialized_result)

    def get_spawn_state(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "config": self.config,
            "runtime_context": self.runtime_context,
            "factory_module": self.factory_module,
            "factory_qualname": self.factory_qualname,
            "reports_model_class_mapping": self.reports_model_class_mapping,
        }

    def cleanup(self) -> None:
        _close_item_resources(self.module, self.module_state, self.logger, self.module_id)
        self.module = None
        self.module_state = None


_EVENT_UPDATE_INPUT = "__evileye_event_update_input__"
_EVENT_UPDATE_OUTPUT = "__evileye_event_update_output__"


class EventDetectorUpdateWorker(MpWorker):
    """Spawn worker for event modules consuming serializable EventUpdate values."""

    def apply_spawn_state(self, state: dict[str, Any]) -> None:
        self.module_id = state["module_id"]
        self.config = state["config"]
        self.factory_module = state["factory_module"]
        self.factory_qualname = state["factory_qualname"]
        self.module = None
        self.module_state = None
        self.drop_oldest_on_full = False

    def _publish_error(self, message: str) -> None:
        try:
            self.output_queue.put(
                (_EVENT_UPDATE_OUTPUT, "error", str(message)), timeout=1.0
            )
        except Exception:
            if self.logger:
                self.logger.exception(
                    "Event detector %s could not report worker error", self.module_id
                )

    def init_worker(self) -> None:
        try:
            factory = importlib.import_module(self.factory_module)
            for component in self.factory_qualname.split("."):
                factory = getattr(factory, component)
            self.module = _call_factory(factory, self.config)
            if not callable(getattr(self.module, "process_update", None)):
                raise PluginError(
                    f"Event detector '{self.module_id}' must implement "
                    "process_update(update, state)"
                )
            context = ModuleRuntimeContext(
                module_id=self.module_id, execution_mode="process"
            )
            self.module_state = _create_state(self.module, self.config, context)
            start = getattr(self.module, "start", None)
            if callable(start):
                start()
            self.output_queue.put(
                (_EVENT_UPDATE_OUTPUT, "ready", None), timeout=1.0
            )
        except Exception as exc:
            self._publish_error(f"Worker initialization failed: {exc}")
            _close_item_resources(self.module, self.module_state, self.logger, self.module_id)
            self.module = None
            self.module_state = None
            raise

    def worker_impl(self, data):
        if not (
            isinstance(data, tuple)
            and len(data) == 2
            and data[0] == _EVENT_UPDATE_INPUT
        ):
            self._stop_event.set()
            return (_EVENT_UPDATE_OUTPUT, "error", "invalid event update envelope")
        try:
            update = pickle.loads(data[1])
            if not isinstance(update, EventUpdate):
                raise PluginError(
                    f"Event detector '{self.module_id}' input must be EventUpdate"
                )
            result = self.module.process_update(update, self.module_state)
            events = [] if result is None else (
                list(result) if isinstance(result, (tuple, list)) else [result]
            )
            payload = _serialize_process_value(
                events, self.module_id, "process_update result"
            )
            return (_EVENT_UPDATE_OUTPUT, "output", payload)
        except Exception as exc:
            if self.logger:
                self.logger.exception(
                    "Event detector %s failed while processing update", self.module_id
                )
            self._stop_event.set()
            return (_EVENT_UPDATE_OUTPUT, "error", str(exc))

    def get_spawn_state(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "config": self.config,
            "factory_module": self.factory_module,
            "factory_qualname": self.factory_qualname,
        }

    def cleanup(self) -> None:
        stop = getattr(self.module, "stop", None)
        if callable(stop):
            try:
                stop()
            except Exception:
                if self.logger:
                    self.logger.exception("Event detector %s failed to stop", self.module_id)
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
        self.source_ids: tuple[int, ...] = ()
        self.worker_count = 1
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
        self.input_queue_dropped = 0
        self.input_queue_rejected = 0
        self._failure_reported = False
        self._model_class_mapping: dict[str, int] | None = None
        self._model_class_mapping_lock = threading.Lock()
        self.reports_model_class_mapping = (
            "model_class_mapping" in capabilities
        )
        self.ResultType = getattr(factory, "ResultType", None)
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
        default_mode = (
            self.registered_module.spec.default_execution_mode
            or tuple(self.registered_module.spec.execution_modes)[0]
        )
        self.execution_mode = str(
            params.get("execution_mode", default_mode)
        ).lower()
        self.source_ids = tuple(
            int(item) for item in (params.get("source_ids") or ())
        )
        self._queue_size = max(1, int(params.get("queue_size", 8)))
        self._config = dict(params.get("config") or {})
        capabilities = set(self.registered_module.spec.capabilities or ())
        requested_workers = int(params.get("worker_count", 1))
        if requested_workers > 1 and "parallel_items" not in capabilities:
            raise PluginError(
                f"Module '{self.module_id}' must declare parallel_items to use "
                "worker_count greater than one"
            )
        reserved = {"type", "module_id", "execution_mode", "source_ids", "queue_size", "ipc_mode", "worker_count"}
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        self._input_queue = queue.Queue(maxsize=self._queue_size)
        self._output_queue = queue.Queue(maxsize=self._queue_size)
        self.input_queue_dropped = 0
        self.input_queue_rejected = 0

    def get_params_impl(self):
        return dict(self.params or {})

    def get_source_ids(self):
        return list(self.source_ids)

    def _record_input_drop(self) -> None:
        self.input_queue_dropped += 1
        self.degraded = True
        self.logger.warning(
            "Plugin module %s dropped stale frame input (dropped=%d)",
            self.module_id,
            self.input_queue_dropped,
        )

    def _enqueue_input(self, item: Any, payload: Any) -> Any | None:
        if self.execution_mode == "process":
            if self._mp_control is None:
                raise RuntimeError(
                    f"Process module '{self.module_id}' is not started"
                )
            if _is_frame_work_item(item):
                dropped, dropped_payload = self._mp_control.put_drop_oldest(payload)
                if dropped:
                    self._record_input_drop()
                    return dropped_payload
            else:
                self._mp_control.put(payload, block=False)
            return None

        try:
            self._input_queue.put_nowait(payload)
            return None
        except queue.Full:
            if not _is_frame_work_item(item):
                raise

        dropped_payload = None
        try:
            dropped_payload = self._input_queue.get_nowait()
        except queue.Empty:
            pass
        self._input_queue.put_nowait(payload)
        if dropped_payload is not None:
            self._record_input_drop()
        return dropped_payload

    def get_model_class_mapping(self) -> dict[str, int] | None:
        with self._model_class_mapping_lock:
            return dict(self._model_class_mapping) if self._model_class_mapping is not None else None

    def _set_model_class_mapping(self, mapping: Any) -> None:
        normalized = _normalize_model_class_mapping(mapping, self.module_id)
        if normalized is None:
            return
        with self._model_class_mapping_lock:
            if self._model_class_mapping is not None and self._model_class_mapping != normalized:
                self.degraded = True
                self.logger.error(
                    "Plugin module %s changed its model class mapping while running",
                    self.module_id,
                )
                return
            self._model_class_mapping = normalized

    def _refresh_thread_model_class_mapping(self) -> None:
        mapping = _get_model_class_mapping(self._module, self.module_id)
        if mapping:
            self._set_model_class_mapping(mapping)

    def _module_runtime_context(self) -> ModuleRuntimeContext:
        return ModuleRuntimeContext(
            module_id=self.registered_module.qualified_id,
            execution_mode=self.execution_mode,
            source_ids=self.source_ids,
            worker_count=self.worker_count,
        )

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
        if self.execution_mode == "process":
            _serialize_process_value(
                self._config, self.module_id, "configuration"
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
            worker.runtime_context = self._module_runtime_context()
            worker.factory_module = self.registered_module.spec.factory.__module__
            worker.factory_qualname = self.registered_module.spec.factory.__qualname__
            worker.module = None
            worker.module_state = None
            worker.drop_oldest_on_full = False
            worker.reports_model_class_mapping = self.reports_model_class_mapping
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
                _validate_model_class_mapping_capability(
                    self._module,
                    self.module_id,
                    self.reports_model_class_mapping,
                )
                self._state = _create_state(
                    self._module, self._config, self._module_runtime_context()
                )
                self._refresh_thread_model_class_mapping()
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
                    self._refresh_thread_model_class_mapping()
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
            payload = item
            if self.execution_mode == "process":
                if self._mp_control is None:
                    raise RuntimeError(
                        f"Process module '{self.module_id}' is not started"
                    )
                serialized_item = _serialize_process_value(
                    item, self.module_id, "input item"
                )
                payload = (_PROCESS_INPUT_MARKER, serialized_item)
            self._enqueue_input(item, payload)
        except queue.Full:
            self.input_queue_rejected += 1
            self.degraded = True
            self.logger.error("Plugin module %s input queue is full", self.module_id)
            raise RuntimeError(f"Plugin module '{self.module_id}' input queue is full")
        except PluginError as exc:
            self.degraded = True
            self.logger.error("%s", exc)
            raise

    def get(self):
        self._check_process_health()
        try:
            if self.execution_mode == "process":
                if self._mp_control is None:
                    return None
                while True:
                    result = self._mp_control.get_nowait()
                    if not (
                        isinstance(result, tuple)
                        and len(result) == 3
                        and result[0] == _PROCESS_OUTPUT_MARKER
                    ):
                        self.degraded = True
                        self.logger.error(
                            "Plugin module %s returned an invalid process envelope",
                            self.module_id,
                        )
                        return None
                    if result[1] == "metadata":
                        try:
                            self._set_model_class_mapping(pickle.loads(result[2]))
                        except Exception as exc:
                            self.degraded = True
                            self.logger.error(
                                "Plugin module %s returned invalid class mapping metadata: %s",
                                self.module_id,
                                exc,
                            )
                        continue
                    if result[1] == "error":
                        self.degraded = True
                        self.logger.error(
                            "Plugin module %s failed in worker: %s", self.module_id, result[2]
                        )
                        return None
                    if result[1] == "output":
                        try:
                            return pickle.loads(result[2])
                        except Exception as exc:
                            self.degraded = True
                            self.logger.error(
                                "Plugin module %s returned an invalid serialized output: %s",
                                self.module_id,
                                exc,
                            )
                            return None
                    self.degraded = True
                    self.logger.error(
                        "Plugin module %s returned an unknown process envelope",
                        self.module_id,
                    )
                    return None
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
            "input_queue_dropped": self.input_queue_dropped,
            "input_queue_rejected": self.input_queue_rejected,
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
        self.input_queue_dropped = 0
        self.input_queue_rejected = 0
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


_ORDERED_THREAD_OUTPUT_MARKER = "__evileye_parallel_item_runtime__"
_ORDERED_SKIP = object()


class OrderedItemModuleWorker(ItemModuleWorker):
    """Process worker that returns each item with its input sequence number."""

    def worker_impl(self, data):
        if not (
            isinstance(data, tuple)
            and len(data) == 3
            and data[0] == _PROCESS_INPUT_MARKER
        ):
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", "invalid ordered input envelope")
        sequence = int(data[1])
        try:
            item = pickle.loads(data[2])
            result = self.module.process_item(item, self.module_state)
            self._publish_model_class_mapping()
            if result is None:
                return (_PROCESS_OUTPUT_MARKER, "skip", sequence, None)
            payload = _serialize_process_value(
                result, self.module_id, "process_item result"
            )
            return (_PROCESS_OUTPUT_MARKER, "output", sequence, payload)
        except Exception as exc:
            if self.logger:
                self.logger.exception(
                    "Plugin module %s failed while processing ordered item %s",
                    self.module_id,
                    sequence,
                )
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", sequence, str(exc))


class ParallelItemModuleAdapter(ItemModuleAdapter):
    """Run explicitly parallel-safe item modules across ordered workers."""

    def __init__(self, registered_module):
        super().__init__(registered_module)
        self.worker_count = 1
        self._parallel_threads: list[threading.Thread] = []
        self._parallel_modules: list[Any] = []
        self._parallel_states: list[Any] = []
        self._next_input_sequence = 0
        self._next_output_sequence = 0
        self._ordered_results: dict[int, Any] = {}

    def set_params_impl(self):
        super().set_params_impl()
        params = dict(self.params or {})
        capabilities = set(self.registered_module.spec.capabilities or ())
        configured_count = params.get(
            "worker_count",
            params.get("num_detection_threads", self._config.get("worker_count", 1)),
        )
        self.worker_count = int(configured_count)
        if self.worker_count < 1:
            raise PluginError("worker_count must be a positive integer")
        if self.worker_count > 1 and "parallel_items" not in capabilities:
            raise PluginError(
                f"Module '{self.module_id}' must declare parallel_items to use "
                "worker_count greater than one"
            )
        self._config.pop("worker_count", None)
        self._config.pop("num_detection_threads", None)
        self._next_input_sequence = 0
        self._next_output_sequence = 0
        self._ordered_results.clear()

    def start(self):
        if self.worker_count == 1:
            return super().start()
        self._stop_event.clear()
        self._failure_reported = False
        if self.execution_mode == "process":
            from .mp_control import MpControl

            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Plugin-{self.module_id.replace('/', '-')}Pool",
                restart_on_exit=False,
            )
            for _ in range(self.worker_count):
                worker = self._mp_control.add_worker(OrderedItemModuleWorker)
                worker.module_id = self.module_id
                worker.config = self._config
                worker.runtime_context = self._module_runtime_context()
                worker.factory_module = self.registered_module.spec.factory.__module__
                worker.factory_qualname = self.registered_module.spec.factory.__qualname__
                worker.module = None
                worker.module_state = None
                worker.drop_oldest_on_full = False
                worker.reports_model_class_mapping = self.reports_model_class_mapping
            self._mp_control.start()
            return

        self._parallel_modules = [None] * self.worker_count
        self._parallel_states = [None] * self.worker_count
        self._parallel_threads = [
            threading.Thread(
                target=self._run_parallel_thread,
                args=(index,),
                name=f"Plugin-{self.module_id.replace('/', '-')}-{index}",
                daemon=True,
            )
            for index in range(self.worker_count)
        ]
        for thread in self._parallel_threads:
            thread.start()
        self._thread = self._parallel_threads[0]

    def _run_parallel_thread(self, worker_index: int):
        module = None
        state = None
        try:
            try:
                module = _call_factory(
                    self.registered_module.spec.factory, self._config
                )
                if not callable(getattr(module, "process_item", None)):
                    raise PluginError(
                        f"Module '{self.module_id}' must implement process_item(item, state)"
                    )
                _validate_model_class_mapping_capability(
                    module, self.module_id, self.reports_model_class_mapping
                )
                state = _create_state(
                    module, self._config, self._module_runtime_context()
                )
                self._parallel_modules[worker_index] = module
                self._parallel_states[worker_index] = state
                if worker_index == 0:
                    self._module = module
                    self._state = state
                mapping = _get_model_class_mapping(module, self.module_id)
                if mapping:
                    self._set_model_class_mapping(mapping)
            except Exception as exc:
                self.degraded = True
                self.logger.exception(
                    "Plugin module %s worker %s failed during initialization",
                    self.module_id,
                    worker_index,
                )
                self._output_queue.put(
                    (_ORDERED_THREAD_OUTPUT_MARKER, "error", str(exc))
                )
                return

            while not self._stop_event.is_set():
                try:
                    sequence, item = self._input_queue.get(timeout=0.1)
                except queue.Empty:
                    continue
                try:
                    result = module.process_item(item, state)
                    mapping = _get_model_class_mapping(module, self.module_id)
                    if mapping:
                        self._set_model_class_mapping(mapping)
                    if result is None:
                        envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "skip", sequence, None)
                    else:
                        envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "output", sequence, result)
                except Exception as exc:
                    self.degraded = True
                    self.logger.exception(
                        "Plugin module %s worker %s failed on item %s",
                        self.module_id,
                        worker_index,
                        sequence,
                    )
                    envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "error", sequence, str(exc))
                    self._stop_event.set()
                while not self._stop_event.is_set():
                    try:
                        self._output_queue.put(envelope, timeout=0.1)
                        break
                    except queue.Full:
                        continue
        finally:
            _close_item_resources(module, state, self.logger, self.module_id)
            self._parallel_modules[worker_index] = None
            self._parallel_states[worker_index] = None
            if worker_index == 0:
                self._module = None
                self._state = None

    def put(self, item):
        if self.worker_count == 1:
            return super().put(item)
        try:
            sequence = self._next_input_sequence
            payload = (sequence, item)
            if self.execution_mode == "process":
                if self._mp_control is None:
                    raise RuntimeError(
                        f"Process module '{self.module_id}' is not started"
                    )
                serialized = _serialize_process_value(
                    item, self.module_id, "input item"
                )
                payload = (_PROCESS_INPUT_MARKER, sequence, serialized)
            dropped_payload = self._enqueue_input(item, payload)
            self._next_input_sequence += 1
            if dropped_payload is not None:
                dropped_sequence = (
                    int(dropped_payload[1])
                    if self.execution_mode == "process"
                    else int(dropped_payload[0])
                )
                self._ordered_results[dropped_sequence] = _ORDERED_SKIP
        except queue.Full:
            self.input_queue_rejected += 1
            self.degraded = True
            self.logger.error("Plugin module %s input queue is full", self.module_id)
            raise RuntimeError(f"Plugin module '{self.module_id}' input queue is full")
        except PluginError as exc:
            self.degraded = True
            self.logger.error("%s", exc)
            raise

    def _store_ordered_message(self, result, *, process_mode: bool) -> None:
        expected_marker = _PROCESS_OUTPUT_MARKER if process_mode else _ORDERED_THREAD_OUTPUT_MARKER
        if not isinstance(result, tuple) or not result or result[0] != expected_marker:
            self.degraded = True
            self.logger.error("Plugin module %s returned an invalid ordered envelope", self.module_id)
            return
        if process_mode and len(result) == 3 and result[1] == "metadata":
            try:
                self._set_model_class_mapping(pickle.loads(result[2]))
            except Exception as exc:
                self.degraded = True
                self.logger.error("Plugin module %s returned invalid class mapping metadata: %s", self.module_id, exc)
            return
        if len(result) == 3 and result[1] == "error":
            self.degraded = True
            self.logger.error("Plugin module %s worker failed: %s", self.module_id, result[2])
            return
        if len(result) != 4:
            self.degraded = True
            self.logger.error("Plugin module %s returned malformed ordered output", self.module_id)
            return
        kind, sequence, payload = result[1], int(result[2]), result[3]
        if sequence in self._ordered_results:
            self.degraded = True
            self.logger.error("Plugin module %s returned item %s more than once", self.module_id, sequence)
            return
        if kind == "skip":
            self._ordered_results[sequence] = _ORDERED_SKIP
        elif kind == "error":
            self._ordered_results[sequence] = ("error", payload)
        elif kind == "output":
            try:
                self._ordered_results[sequence] = pickle.loads(payload) if process_mode else payload
            except Exception as exc:
                self._ordered_results[sequence] = ("error", str(exc))
        else:
            self.degraded = True
            self.logger.error("Plugin module %s returned unknown ordered output kind %s", self.module_id, kind)

    def get(self):
        if self.worker_count == 1:
            return super().get()
        if self.execution_mode == "process":
            self._check_process_health()
            if self._mp_control is None:
                return None
            for _ in range(max(16, self._queue_size * 2)):
                try:
                    self._store_ordered_message(
                        self._mp_control.get_nowait(), process_mode=True
                    )
                except queue.Empty:
                    break
        else:
            for _ in range(max(16, self._queue_size * 2)):
                try:
                    self._store_ordered_message(
                        self._output_queue.get_nowait(), process_mode=False
                    )
                except queue.Empty:
                    break
        while self._next_output_sequence in self._ordered_results:
            value = self._ordered_results.pop(self._next_output_sequence)
            self._next_output_sequence += 1
            if value is _ORDERED_SKIP:
                continue
            if isinstance(value, tuple) and len(value) == 2 and value[0] == "error":
                self.degraded = True
                self.logger.error("Plugin module %s failed on ordered item: %s", self.module_id, value[1])
                return None
            return value
        return None

    def stop(self):
        if self.worker_count == 1 or self.execution_mode == "process":
            return super().stop()
        self._stop_event.set()
        for thread in self._parallel_threads:
            if thread.is_alive():
                thread.join(timeout=2.0)
        self._parallel_threads = []
        self._thread = None

    def get_runtime_stats(self) -> dict[str, Any]:
        stats = super().get_runtime_stats()
        stats["worker_count"] = self.worker_count
        if self.execution_mode == "thread" and self.worker_count > 1:
            stats["worker_running"] = sum(
                thread.is_alive() for thread in self._parallel_threads
            )
        return stats


class BatchProcessorModuleAdapter(EvilEyeBase):
    """Adapt a synchronous, thread-only ``process_batch`` plugin to a pipeline stage."""

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids: list[int] = []
        self._config: dict[str, Any] = {}
        self._module = None
        self._state = None
        self.degraded = False
        super().__init__()

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        self.execution_mode = str(params.get("execution_mode", "thread")).strip().lower()
        if self.execution_mode != "thread":
            raise PluginError(
                f"Batch processor '{self.module_id}' supports thread execution only"
            )
        self.source_ids = [int(item) for item in (params.get("source_ids") or [])]
        self._config = dict(params.get("config") or {})
        reserved = {"type", "module_id", "execution_mode", "source_ids", "config", "queue_size", "ipc_mode"}
        for key, value in params.items():
            if key not in reserved:
                self._config.setdefault(key, value)
        self._module = _call_factory(self.registered_module.spec.factory, self._config)
        if not callable(getattr(self._module, "process_batch", None)):
            raise PluginError(
                f"Batch processor '{self.registered_module.qualified_id}' must implement process_batch(batch, state)"
            )
        module_params = dict(params)
        module_params.pop("module_id", None)
        module_params.pop("config", None)
        module_params.setdefault("type", self.module_id.rsplit("/", 1)[-1])
        set_params = getattr(self._module, "set_params", None)
        if callable(set_params):
            set_params(**module_params)

    def get_params_impl(self):
        return dict(self.params or {})

    def get_source_ids(self):
        callback = getattr(self._module, "get_source_ids", None)
        if callable(callback):
            return callback()
        return self.source_ids

    def init_impl(self, **kwargs):
        if self.execution_mode != "thread":
            raise PluginError(
                f"Batch processor '{self.module_id}' supports thread execution only"
            )
        init = getattr(self._module, "init", None)
        if callable(init):
            result = init(**kwargs)
            if result is False:
                return False
        context = ModuleRuntimeContext(
            module_id=self.registered_module.qualified_id,
            execution_mode=self.execution_mode,
            source_ids=tuple(self.source_ids),
        )
        self._state = _create_state(self._module, self._config, context)
        return True

    def process_batch(self, batch):
        try:
            return self._module.process_batch(batch, self._state)
        except Exception:
            self.degraded = True
            self.logger.exception("Batch plugin %s failed while processing a batch", self.module_id)
            raise

    def get_runtime_stats(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "module_initialized": self._module is not None,
            "degraded": self.degraded,
        }

    def start(self):
        callback = getattr(self._module, "start", None)
        if callable(callback):
            callback()

    def stop(self):
        callback = getattr(self._module, "stop", None)
        if callable(callback):
            callback()

    def default(self):
        self.reset_impl()

    def reset_impl(self):
        callback = getattr(self._module, "reset", None)
        if callable(callback):
            callback()
        self.degraded = False

    def release_impl(self):
        self.stop()
        _close_item_resources(self._module, self._state, self.logger, self.module_id)
        self._module = None
        self._state = None

    def __getattr__(self, name: str):
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(name)


class LegacyProcessorModuleAdapter(EvilEyeBase):
    """Expose an existing queue/lifecycle processor through the module SPI.

    This bridge lets established model, tracker, and attribute implementations
    keep their proven worker internals while pipelines resolve them through the
    same namespaced registry used by external modules.
    """

    def __init__(self, registered_module):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.execution_mode = "thread"
        self.source_ids = []
        self._module = None
        super().__init__()
        self.ResultType = getattr(registered_module.spec.factory, "ResultType", None)
        self._module = _call_factory(registered_module.spec.factory, {})

    def set_id(self, id_value: int):
        super().set_id(id_value)
        if self._module is not None and callable(getattr(self._module, "set_id", None)):
            self._module.set_id(id_value)

    def set_params_impl(self):
        params = dict(self.params or {})
        self.module_id = str(params.get("module_id") or params.get("type") or self.module_id)
        supported_modes = tuple(self.registered_module.spec.execution_modes)
        default_mode = self.registered_module.spec.default_execution_mode
        if default_mode is None:
            default_mode = "process" if "process" in supported_modes else supported_modes[0]
        self.execution_mode = str(params.get("execution_mode", default_mode)).lower()
        self.source_ids = list(params.get("source_ids") or [])
        module_params = dict(params)
        module_params.pop("module_id", None)
        module_params.setdefault("type", self.module_id.rsplit("/", 1)[-1])
        self._module.set_params(**module_params)
        if callable(getattr(self._module, "set_id", None)):
            self._module.set_id(self.id)

    def get_params_impl(self):
        return self._module.get_params()

    def init_impl(self, **kwargs):
        if self.execution_mode not in self.registered_module.spec.execution_modes:
            raise PluginError(
                f"Module '{self.module_id}' does not support execution_mode="
                f"'{self.execution_mode}'"
            )
        initialized = self._module.init(**kwargs)
        if initialized is None:
            return bool(self._module.get_init_flag())
        return bool(initialized)

    def start(self):
        return self._module.start()

    def stop(self):
        return self._module.stop()

    def put(self, item, *args, **kwargs):
        return self._module.put(item, *args, **kwargs)

    def get(self, *args, **kwargs):
        return self._module.get(*args, **kwargs)

    def get_source_ids(self):
        callback = getattr(self._module, "get_source_ids", None)
        if callable(callback):
            return callback()
        return self.source_ids

    def get_dropped_ids(self):
        callback = getattr(self._module, "get_dropped_ids", None)
        return callback() if callable(callback) else []

    def set_class_manager(self, class_manager):
        callback = getattr(self._module, "set_class_manager", None)
        if callable(callback):
            callback(class_manager)

    def set_system_event_callback(self, callback):
        handler = getattr(self._module, "set_system_event_callback", None)
        if callable(handler):
            handler(callback)

    def get_debug_info(self, debug_info: dict | None):
        callback = getattr(self._module, "get_debug_info", None)
        if callable(callback):
            callback(debug_info if debug_info is not None else {})
        else:
            super().get_debug_info(debug_info)

    def calc_memory_consumption(self):
        callback = getattr(self._module, "calc_memory_consumption", None)
        if callable(callback):
            callback()
            self.memory_measure_results = getattr(self._module, "memory_measure_results", None)
            self.memory_measure_time = getattr(self._module, "memory_measure_time", None)
        else:
            super().calc_memory_consumption()

    def release_impl(self):
        if self._module is not None:
            self._module.release()

    def reset_impl(self):
        if self._module is not None:
            self._module.reset()

    def default(self):
        if self._module is not None:
            self._module.default()

    def __getattr__(self, name: str):
        module = self.__dict__.get("_module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(name)


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


class EventDetectorModuleAdapter(EvilEyeBase):
    """Own event-detector construction, config, and thread/process lifecycle."""

    def __init__(self, registered_module, context):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.context = context
        self.module = None
        self._config: dict[str, Any] = {}
        self._started = False
        self.execution_mode = "thread"
        self.degraded = False
        self.last_error = None
        self._queue_size = 32
        self._mp_control = None
        self._update_thread = None
        self._update_stop = threading.Event()
        self._update_notifications: queue.Queue = queue.Queue(maxsize=self._queue_size)
        self._pending_process_updates: queue.Queue = queue.Queue(maxsize=self._queue_size)
        self._notifications_dropped = 0
        self._process_updates_dropped = 0
        self._sequence = 0
        self._updates_submitted = 0
        self._events_received = 0
        self._failure_reported = False
        self._closing = False
        self._stopped_events: list[Any] = []
        super().__init__()
        if not registered_module.spec.execution_modes:
            raise PluginError(
                f"Event detector '{self.module_id}' declares no execution modes"
            )

    def _record_failure(self, operation: str, exc: Exception) -> None:
        self.degraded = True
        self.last_error = f"{operation}: {type(exc).__name__}: {exc}"
        self.logger.error(
            "Event detector '%s' %s failed: %s",
            self.module_id,
            operation,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    def _call_module(self, operation: str, *args, **kwargs):
        if self.module is None:
            raise PluginError(f"Event detector '{self.module_id}' is not initialized")
        method = getattr(self.module, operation)
        try:
            return method(*args, **kwargs)
        except Exception as exc:
            self._record_failure(operation, exc)
            raise PluginError(
                f"Event detector '{self.module_id}' {operation} failed: {exc}"
            ) from exc

    def default(self):
        if self.module is not None and callable(getattr(self.module, "default", None)):
            return self._call_module("default")
        return {}

    def get_params_impl(self):
        if self.module is not None and callable(getattr(self.module, "get_params", None)):
            return self._call_module("get_params")
        return dict(self._config)

    def set_params_impl(self):
        params = dict(self.params or {})
        spec = self.registered_module.spec
        default_mode = spec.default_execution_mode
        if default_mode is None:
            default_mode = "thread" if "thread" in spec.execution_modes else spec.execution_modes[0]
        requested_mode = str(params.get("execution_mode") or default_mode).strip().lower()
        if requested_mode not in spec.execution_modes:
            raise PluginError(
                f"Event detector '{self.module_id}' does not support "
                f"execution_mode='{requested_mode}'; supported modes: "
                f"{', '.join(spec.execution_modes)}"
            )
        self.execution_mode = requested_mode
        capabilities = set(spec.capabilities)
        if requested_mode == "process":
            input_capabilities = capabilities.intersection(
                {"event_updates", "event_commands"}
            )
            if not input_capabilities:
                raise PluginError(
                    f"Process event detector '{self.module_id}' must declare "
                    "event_updates or event_commands"
                )
            live_capabilities = capabilities.intersection(
                {"object_handler", "capture_sources"}
            )
            if live_capabilities:
                raise PluginError(
                    f"Process event detector '{self.module_id}' cannot declare live "
                    f"dependencies: {', '.join(sorted(live_capabilities))}; use "
                    "event_updates and the EventUpdate contract"
                )
        reserved = {
            "module_id", "type", "execution_mode", "logger_name",
            "queue_size", "config",
        }
        config = params.get("config")
        if config is None:
            config = {key: value for key, value in params.items() if key not in reserved}
        if not isinstance(config, dict):
            raise PluginError(f"Event detector '{self.module_id}' config must be an object")
        self._config = dict(config)
        self._queue_size = max(1, int(params.get("queue_size", 32)))
        if requested_mode == "process":
            self._update_notifications = queue.Queue(maxsize=self._queue_size)
            self._pending_process_updates = queue.Queue(maxsize=self._queue_size)
        if spec.config_schema is not None:
            self._config = plugin_registry.validate_module_config(
                self.module_id, self._config
            )
        if requested_mode == "process":
            _serialize_process_value(
                self._config, self.module_id, "configuration"
            )

    def init_impl(self, **kwargs):
        if self.execution_mode == "process":
            return True
        factory = self.registered_module.spec.factory
        try:
            self.module = factory(self.context)
        except Exception as exc:
            self._record_failure("factory", exc)
            raise PluginError(
                f"Event detector factory '{self.module_id}' failed: {exc}"
            ) from exc
        required = ("set_params", "init", "start", "stop", "reset", "put", "get", "get_name")
        if (
            "object_handler" in self.registered_module.spec.capabilities
            or "capture_sources" in self.registered_module.spec.capabilities
        ):
            required += ("update",)
        missing = [name for name in required if not callable(getattr(self.module, name, None))]
        if missing:
            exc = PluginError(
                f"Event detector '{self.module_id}' is missing contract methods: "
                f"{', '.join(missing)}"
            )
            self._record_failure("contract validation", exc)
            self.module = None
            raise exc
        self._call_module("set_params", **self._config)
        initialized = self._call_module("init")
        if initialized is False:
            self._record_failure("initialization", RuntimeError("init returned false"))
            return False
        return True

    def start(self):
        if not self.is_inited:
            raise PluginError(f"Event detector '{self.module_id}' is not initialized")
        if self._started:
            return
        self._closing = False
        if self.execution_mode == "process":
            from .mp_control import MpControl

            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Event-{self.module_id.replace('/', '-')}",
                restart_on_exit=False,
            )
            worker = self._mp_control.add_worker(EventDetectorUpdateWorker)
            worker.module_id = self.module_id
            worker.config = self._config
            worker.factory_module = self.registered_module.spec.factory.__module__
            worker.factory_qualname = self.registered_module.spec.factory.__qualname__
            worker.module = None
            worker.module_state = None
            worker.drop_oldest_on_full = False
            self._mp_control.start()
            try:
                ready = self._mp_control.output_queue.get(timeout=10.0)
            except queue.Empty as exc:
                self._record_failure(
                    "worker startup", RuntimeError("worker did not become ready in 10 seconds")
                )
                self._mp_control.stop()
                self._mp_control = None
                raise PluginError(
                    f"Process event detector '{self.module_id}' worker startup timed out"
                ) from exc
            if (
                not isinstance(ready, tuple)
                or len(ready) != 3
                or ready[0] != _EVENT_UPDATE_OUTPUT
                or ready[1] != "ready"
            ):
                message = (
                    str(ready[2]) if isinstance(ready, tuple) and len(ready) == 3
                    and ready[1] == "error" else "worker returned an invalid startup envelope"
                )
                self._record_failure("worker startup", RuntimeError(message))
                self._mp_control.stop()
                self._mp_control = None
                raise PluginError(
                    f"Process event detector '{self.module_id}' worker failed to start: {message}"
                )
            self._started = True
            try:
                self._flush_pending_process_updates()
            except Exception:
                self._started = False
                self._mp_control.stop()
                self._mp_control = None
                raise
            if "event_updates" in self.registered_module.spec.capabilities:
                self._update_stop.clear()
                self._update_thread = threading.Thread(
                    target=self._dispatch_context_updates,
                    name=f"EventUpdates-{self.module_id.replace('/', '-')}",
                    daemon=True,
                )
                self._update_thread.start()
        else:
            self._call_module("start")
            self._started = True

    def _snapshot_value(self, value: Any) -> Any:
        import datetime
        import math

        if value is None or isinstance(value, (str, bool, int)):
            return value
        if isinstance(value, float):
            if not math.isfinite(value):
                raise PluginError(
                    f"Event detector '{self.module_id}' update contains non-finite number"
                )
            return value
        if isinstance(value, datetime.datetime):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {
                str(key): self._snapshot_value(item)
                for key, item in value.items()
                if not str(key).startswith("_")
            }
        if isinstance(value, (tuple, list)):
            return [self._snapshot_value(item) for item in value]
        if isinstance(value, set):
            return [self._snapshot_value(item) for item in sorted(value, key=str)]
        tolist = getattr(value, "tolist", None)
        if callable(tolist):
            return self._snapshot_value(tolist())
        item = getattr(value, "item", None)
        if callable(item):
            return self._snapshot_value(item())
        raise PluginError(
            f"Event detector '{self.module_id}' update contains unsupported value "
            f"{type(value).__name__}"
        )

    def _snapshot_object(self, obj: Any) -> dict[str, Any]:
        def _entry(value: Any) -> dict[str, Any]:
            track = getattr(value, "track", None)
            bbox = getattr(track, "bounding_box", None) if track is not None else None
            return {
                "object_id": self._snapshot_value(getattr(value, "object_id", None)),
                "global_id": self._snapshot_value(getattr(value, "global_id", None)),
                "source_id": self._snapshot_value(getattr(value, "source_id", None)),
                "class_id": self._snapshot_value(getattr(value, "class_id", None)),
                "frame_id": self._snapshot_value(getattr(value, "frame_id", None)),
                "timestamp": self._snapshot_value(getattr(value, "time_stamp", None)),
                "bbox": self._snapshot_value(bbox) if bbox is not None else None,
            }

        track = getattr(obj, "track", None)
        bbox = getattr(track, "bounding_box", None) if track is not None else None
        history = getattr(obj, "history", ()) or ()
        return {
            "object_id": self._snapshot_value(getattr(obj, "object_id", None)),
            "global_id": self._snapshot_value(getattr(obj, "global_id", None)),
            "source_id": self._snapshot_value(getattr(obj, "source_id", None)),
            "class_id": self._snapshot_value(getattr(obj, "class_id", None)),
            "frame_id": self._snapshot_value(getattr(obj, "frame_id", None)),
            "timestamp": self._snapshot_value(getattr(obj, "time_stamp", None)),
            "bbox": self._snapshot_value(bbox) if bbox is not None else None,
            "attributes": self._snapshot_value(getattr(obj, "attributes", {}) or {}),
            "history": [_entry(item) for item in history],
        }

    def _build_context_updates(self) -> list[EventUpdate]:
        import datetime

        handler = getattr(self.context, "objects_handler", None)
        if handler is None:
            raise PluginError(
                f"Process event detector '{self.module_id}' requires objects_handler "
                "to build event_updates"
            )
        updates = []
        for source_id in self.context.pipeline_source_ids:
            active = handler.get("active", source_id)
            lost = handler.get("lost", source_id)
            active_objects = getattr(active, "objects", ()) if active is not None else ()
            lost_objects = getattr(lost, "objects", ()) if lost is not None else ()
            update = EventUpdate(
                sequence=self._sequence,
                kind="object_snapshot",
                source_id=int(source_id),
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                payload={
                    "active": [self._snapshot_object(obj) for obj in active_objects],
                    "lost": [self._snapshot_object(obj) for obj in lost_objects],
                },
            )
            self._sequence += 1
            updates.append(update)
        return updates

    def _dispatch_context_updates(self):
        while not self._update_stop.is_set():
            try:
                self._update_notifications.get(timeout=0.1)
            except queue.Empty:
                continue
            if self._update_stop.is_set():
                break
            try:
                for update in self._build_context_updates():
                    self.put(update)
            except Exception as exc:
                self._record_failure("event update dispatch", exc)

    def _enqueue_process_update(self, update: EventUpdate) -> None:
        if not isinstance(update, EventUpdate):
            raise PluginError(
                f"Process event detector '{self.module_id}' accepts EventUpdate values"
            )
        payload = _serialize_process_value(update, self.module_id, "EventUpdate input")
        if self._closing:
            self._record_failure(
                "input queue", RuntimeError("event detector is stopping; update was rejected")
            )
            raise PluginError(
                f"Process event detector '{self.module_id}' is stopping"
            )
        if self._mp_control is None or not self._started:
            try:
                self._pending_process_updates.put_nowait(update)
                return
            except queue.Full as exc:
                self._process_updates_dropped += 1
                self._record_failure(
                    "pre-start input queue",
                    RuntimeError("event update queue is full; update was rejected"),
                )
                raise PluginError(
                    f"Process event detector '{self.module_id}' pre-start input queue is full"
                ) from exc
        self._send_process_payload(payload)

    def _send_process_payload(self, payload: bytes) -> None:
        try:
            self._mp_control.put(
                (_EVENT_UPDATE_INPUT, payload), block=False
            )
            self._updates_submitted += 1
        except queue.Full as exc:
            self._record_failure(
                "input queue",
                RuntimeError("event update queue is full; update was rejected"),
            )
            raise PluginError(
                f"Process event detector '{self.module_id}' input queue is full"
            ) from exc

    def _flush_pending_process_updates(self) -> None:
        while True:
            try:
                update = self._pending_process_updates.get_nowait()
            except queue.Empty:
                return
            payload = _serialize_process_value(
                update, self.module_id, "EventUpdate input"
            )
            self._send_process_payload(payload)

    def put(self, data):
        if self.execution_mode == "process":
            return self._enqueue_process_update(data)
        return self._call_module("put", data)

    def _collect_process_output(self, control) -> list[Any]:
        events = []
        for _ in range(max(16, self._queue_size * 2)):
            try:
                envelope = control.get_nowait()
            except queue.Empty:
                break
            if (
                not isinstance(envelope, tuple)
                or len(envelope) != 3
                or envelope[0] != _EVENT_UPDATE_OUTPUT
            ):
                self._record_failure(
                    "worker output", RuntimeError("worker returned an invalid envelope")
                )
                continue
            if envelope[1] == "error":
                self._record_failure("worker", RuntimeError(str(envelope[2])))
                self._failure_reported = True
                continue
            if envelope[1] != "output":
                self._record_failure(
                    "worker output", RuntimeError(f"unknown envelope kind {envelope[1]!r}")
                )
                continue
            try:
                events.extend(pickle.loads(envelope[2]))
                self._events_received += 1
            except Exception as exc:
                self._record_failure("worker output deserialization", exc)
        return events

    def get(self):
        if self.execution_mode != "process":
            return self._call_module("get")
        events, self._stopped_events = self._stopped_events, []
        if self._mp_control is not None:
            events.extend(self._collect_process_output(self._mp_control))
        self._check_process_health()
        return events

    def _stop_process_worker(self) -> None:
        control = self._mp_control
        if control is None:
            return
        processes = list(control.processes)
        deadline = time.monotonic() + 5.0
        poison_sent = False
        while (
            any(process.is_alive() for process in processes)
            and not poison_sent
            and time.monotonic() < deadline
        ):
            try:
                control.input_queue.put_nowait(None)
                poison_sent = True
            except queue.Full:
                self._stopped_events.extend(self._collect_process_output(control))
                time.sleep(0.01)
        if not poison_sent and any(process.is_alive() for process in processes):
            self._record_failure(
                "worker shutdown",
                RuntimeError("could not enqueue graceful worker stop marker"),
            )
        while poison_sent and any(process.is_alive() for process in processes):
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                break
            self._stopped_events.extend(self._collect_process_output(control))
            for process in processes:
                if process.is_alive():
                    process.join(timeout=min(0.02, remaining))
        self._stopped_events.extend(self._collect_process_output(control))
        if any(process.is_alive() for process in processes):
            self._record_failure(
                "worker shutdown",
                RuntimeError("worker did not stop within 5 seconds; forced termination required"),
            )
            control.stop(timeout=1.0)
        else:
            control.stop(timeout=1.0)
        if any(process.exitcode not in (0, None) for process in processes):
            self._record_failure(
                "worker shutdown",
                RuntimeError("worker exited abnormally during shutdown"),
            )
        self._mp_control = None

    def _check_process_health(self):
        if self._mp_control is None or not self._started or self._failure_reported:
            return
        exited = [
            process for process in self._mp_control.processes
            if process.exitcode is not None
        ]
        if exited:
            self._failure_reported = True
            self._record_failure(
                "worker exit",
                RuntimeError(f"worker exited unexpectedly with code {exited[0].exitcode}"),
            )

    def update(self):
        if self.execution_mode == "process":
            if "event_updates" not in self.registered_module.spec.capabilities:
                raise PluginError(
                    f"Process event detector '{self.module_id}' does not accept "
                    "ObjectsHandler update notifications"
                )
            try:
                self._update_notifications.put_nowait(True)
            except queue.Full:
                self._notifications_dropped += 1
                self._record_failure(
                    "event update notification",
                    RuntimeError(
                        "host update queue is full; notification was rejected"
                    ),
                )
        elif self.module is not None and callable(getattr(self.module, "update", None)):
            return self._call_module("update")
        return None

    def emit_message(self, event_type: str, message: str):
        if self.execution_mode != "process":
            return self._call_module("emit_message", event_type, message)
        if "event_commands" not in self.registered_module.spec.capabilities:
            raise PluginError(
                f"Process event detector '{self.module_id}' does not accept "
                "controller event commands"
            )
        import datetime

        update = EventUpdate(
            sequence=self._sequence,
            kind="system_message",
            timestamp=datetime.datetime.now().isoformat(),
            payload={
                "event_type": str(event_type),
                "message": str(message),
            },
        )
        self._sequence += 1
        return self.put(update)

    def emit_started(self):
        return self.emit_message("SystemStart", "")

    def emit_stopped(self):
        return self.emit_message("SystemStop", "")

    def get_name(self):
        if self.module is None:
            return self.registered_module.spec.module_id
        return self._call_module("get_name")

    def get_runtime_stats(self) -> dict[str, Any]:
        self._check_process_health()
        worker_running = False
        if self.execution_mode == "process" and self._mp_control is not None:
            worker_running = any(p.is_alive() for p in self._mp_control.processes)
        elif self.module is not None:
            module_stats = getattr(self.module, "get_runtime_stats", None)
            worker_running = self._started
        else:
            module_stats = None
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "initialized": self.is_inited,
            "started": self._started,
            "worker_running": worker_running,
            "updates_submitted": self._updates_submitted,
            "update_notifications_dropped": self._notifications_dropped,
            "process_updates_dropped": self._process_updates_dropped,
            "events_received": self._events_received,
            "degraded": self.degraded,
            "last_error": self.last_error,
            "module": (
                module_stats() if self.execution_mode != "process"
                and callable(module_stats) else None
            ) if self.module is not None else None,
        }

    def get_debug_info(self, debug_info: dict | None):
        if debug_info is None:
            debug_info = {}
        super().get_debug_info(debug_info)
        debug_info["plugin_runtime"] = self.get_runtime_stats()
        return debug_info

    def stop(self):
        if self.execution_mode == "process":
            self._closing = True
            self._update_stop.set()
            if self._update_thread is not None and self._update_thread.is_alive():
                self._update_thread.join(timeout=2.0)
                if self._update_thread.is_alive():
                    self._record_failure(
                        "shutdown", RuntimeError("update dispatcher did not stop in time")
                    )
            self._update_thread = None
            dropped_notifications = 0
            while True:
                try:
                    self._update_notifications.get_nowait()
                    dropped_notifications += 1
                except queue.Empty:
                    break
            if dropped_notifications:
                self._notifications_dropped += dropped_notifications
                self._record_failure(
                    "shutdown",
                    RuntimeError(
                        f"{dropped_notifications} queued host updates were discarded"
                    ),
                )
            dropped_process_updates = 0
            while True:
                try:
                    self._pending_process_updates.get_nowait()
                    dropped_process_updates += 1
                except queue.Empty:
                    break
            if dropped_process_updates:
                self._process_updates_dropped += dropped_process_updates
                self._record_failure(
                    "shutdown",
                    RuntimeError(
                        f"{dropped_process_updates} pre-start event updates were discarded"
                    ),
                )
            if self._mp_control is not None:
                self._stop_process_worker()
        elif self.module is not None and self._started:
            self._call_module("stop")
        self._started = False

    def reset_impl(self):
        self.stop()
        if self.module is not None:
            self._call_module("reset")
        self.degraded = False
        self.last_error = None
        self._failure_reported = False
        self._sequence = 0
        self._updates_submitted = 0
        self._notifications_dropped = 0
        self._process_updates_dropped = 0
        self._events_received = 0

    def release_impl(self):
        self.stop()
        if self.module is not None:
            release = getattr(self.module, "release", None)
            if callable(release):
                self._call_module("release")
            self.module = None
        self.is_inited = False

    def __getattr__(self, name: str):
        module = self.__dict__.get("module")
        if module is not None and hasattr(module, name):
            return getattr(module, name)
        raise AttributeError(name)


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
            module = self._ensure_managed_source_module()
            try:
                module.open()
            except Exception as exc:
                self._mark_degraded(f"capture source could not open: {exc}")
                self.logger.exception("Capture source plugin %s could not open", self.module_id)
                return False
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
        backend_control = getattr(module, "_mp_control", None)
        backend_processes = list(getattr(backend_control, "processes", []) or [])
        try:
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
