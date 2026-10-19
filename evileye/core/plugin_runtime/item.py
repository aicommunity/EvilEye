"""Item processors (``process_item``): error policy, process worker and adapter."""

from __future__ import annotations

import importlib
import pickle
import queue
import threading
import time
from typing import Any, Mapping

from ..base_class import EvilEyeBase
from ..health_window import RollingEventCounter
from ..mp_worker import MpWorker
from ..plugins import ModuleRuntimeContext, PluginError, plugin_registry
from .transport import (
    _IncomingFrameDropped,
    _PROCESS_INPUT_MARKER,
    _PROCESS_OUTPUT_MARKER,
    _PROCESS_RESULT_MARKER,
    _call_factory,
    _close_item_resources,
    _create_state,
    _get_model_class_mapping,
    _is_frame_work_item,
    _normalize_model_class_mapping,
    _prepare_item_for_process,
    _request_id_from_process_payload,
    _restore_process_result,
    _serialize_process_value,
    _validate_model_class_mapping_capability,
)

_ERROR_POLICIES = ("skip_item", "restart", "fail_stop")


_ERROR_POLICY_PARAMS = frozenset({
    "error_policy", "error_burst_limit", "max_restarts", "restart_window_s",
    "mp_restart_on_exit", "mp_no_restart_exit_codes",
})


class _ItemErrorPolicy:
    """How an item module reacts to exceptions raised by ``process_item``.

    ``skip_item`` drops the failing item and escalates to a worker restart after
    ``error_burst_limit`` consecutive failures, ``restart`` recreates the worker
    after every failure and ``fail_stop`` keeps the legacy "stop for good"
    behavior. Restarts are limited to ``max_restarts`` per ``restart_window_s``.
    """

    def __init__(
        self,
        policy: str = "skip_item",
        burst_limit: int = 50,
        max_restarts: int = 5,
        restart_window_s: float = 60.0,
        restart_on_exit: bool | None = None,
        no_restart_exit_codes: Any = None,
    ):
        self.policy = policy
        self.burst_limit = burst_limit
        self.max_restarts = max_restarts
        self.restart_window_s = restart_window_s
        self.restart_on_exit = (
            policy != "fail_stop" if restart_on_exit is None else bool(restart_on_exit)
        )
        self.no_restart_exit_codes = (
            None if no_restart_exit_codes is None else tuple(sorted(no_restart_exit_codes))
        )

    @classmethod
    def from_params(cls, params: Mapping[str, Any], module_id: str) -> "_ItemErrorPolicy":
        policy = params.get("error_policy", "skip_item")
        if policy not in _ERROR_POLICIES:
            raise PluginError(
                f"Module '{module_id}' error_policy must be one of "
                f"{', '.join(_ERROR_POLICIES)}, got {policy!r}"
            )

        def _number(key, default, kind, minimum):
            value = params.get(key, default)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise PluginError(f"Module '{module_id}' {key} must be a number, got {value!r}")
            value = kind(value)
            if value < minimum:
                raise PluginError(f"Module '{module_id}' {key} must be >= {minimum}, got {value!r}")
            return value

        restart_on_exit = params.get("mp_restart_on_exit")
        if restart_on_exit is not None and (
            isinstance(restart_on_exit, bool) is False and restart_on_exit not in (0, 1)
        ):
            raise PluginError(
                f"Module '{module_id}' mp_restart_on_exit must be a boolean, got {restart_on_exit!r}"
            )
        codes = params.get("mp_no_restart_exit_codes")
        if codes is not None:
            raw = codes if isinstance(codes, (list, tuple, set, frozenset)) else [codes]
            if any(isinstance(code, bool) or not isinstance(code, int) for code in raw):
                raise PluginError(
                    f"Module '{module_id}' mp_no_restart_exit_codes must be an integer "
                    f"or a list of integers, got {codes!r}"
                )
            codes = set(raw)
        return cls(
            policy=policy,
            burst_limit=_number("error_burst_limit", 50, int, 1),
            max_restarts=_number("max_restarts", 5, int, 0),
            restart_window_s=_number("restart_window_s", 60.0, float, 0.0),
            restart_on_exit=None if restart_on_exit is None else bool(restart_on_exit),
            no_restart_exit_codes=codes,
        )

    def to_state(self) -> dict[str, Any]:
        return {
            "policy": self.policy,
            "burst_limit": self.burst_limit,
            "max_restarts": self.max_restarts,
            "restart_window_s": self.restart_window_s,
            "restart_on_exit": self.restart_on_exit,
            "no_restart_exit_codes": self.no_restart_exit_codes,
        }

    @classmethod
    def from_state(cls, state: Mapping[str, Any] | None) -> "_ItemErrorPolicy":
        return cls(**dict(state)) if state else cls()

    def mp_control_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {
            "restart_on_exit": self.restart_on_exit,
            "max_restarts": self.max_restarts,
            "restart_window_s": self.restart_window_s,
        }
        if self.no_restart_exit_codes is not None:
            kwargs["no_restart_exit_codes"] = set(self.no_restart_exit_codes)
        return kwargs


class _ItemErrorTracker:
    """Counts consecutive ``process_item`` failures and picks the reaction."""

    def __init__(self, policy: _ItemErrorPolicy):
        self.policy = policy
        self.consecutive = 0
        self.total = 0

    def success(self) -> None:
        self.consecutive = 0

    def failure(self) -> str:
        """Return ``"skip"``, ``"restart"`` or ``"fail"``."""
        self.total += 1
        self.consecutive += 1
        if self.policy.policy == "fail_stop":
            return "fail"
        if self.policy.policy == "restart" or self.consecutive >= self.policy.burst_limit:
            return "restart"
        return "skip"


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
        self.ready_event = state.get("ready_event")
        self.init_failed_event = state.get("init_failed_event")
        self._last_model_class_mapping = None
        self.reports_model_class_mapping = bool(
            state.get("reports_model_class_mapping", False)
        )
        self.error_policy_state = state.get("error_policy")
        self._error_tracker = None

    error_policy_state: dict[str, Any] | None = None
    _error_tracker: _ItemErrorTracker | None = None

    def _tracker(self) -> _ItemErrorTracker:
        if self._error_tracker is None:
            self._error_tracker = _ItemErrorTracker(
                _ItemErrorPolicy.from_state(self.error_policy_state)
            )
        return self._error_tracker

    def _handle_item_failure(self, request_id: int, exc: BaseException):
        """Apply the error policy; returns the envelope to send to the parent."""
        action = self._tracker().failure()
        if action == "restart":
            # The worker exits after delivering this envelope; MpControl restarts it.
            self._stop_event.set()
        elif action == "fail":
            self._stop_event.set()
        payload = pickle.dumps((request_id, str(exc)), protocol=pickle.HIGHEST_PROTOCOL)
        kind = "error" if action == "fail" else "item_error"
        return (_PROCESS_OUTPUT_MARKER, kind, payload)

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
            if self.ready_event is not None:
                self.ready_event.set()
        except Exception as exc:
            if self.init_failed_event is not None:
                self.init_failed_event.set()
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
            isinstance(data, tuple) and len(data) == 3
            and data[0] == _PROCESS_INPUT_MARKER and isinstance(data[1], int)
        ):
            self._stop_event.set()
            return (_PROCESS_OUTPUT_MARKER, "error", "invalid serialized input envelope")
        request_id = data[1]
        try:
            item = pickle.loads(data[2])
            result = self.module.process_item(item, self.module_state)
            self._publish_model_class_mapping()
        except Exception as exc:
            if self.logger:
                self.logger.exception("Plugin module %s failed while processing item", self.module_id)
            return self._handle_item_failure(request_id, exc)
        if result is None:
            self._tracker().success()
            return (_PROCESS_OUTPUT_MARKER, "skip", request_id)
        try:
            serialized_result = _serialize_process_value(
                (_PROCESS_RESULT_MARKER, request_id, result),
                self.module_id,
                "process_item result",
            )
        except PluginError as exc:
            if self.logger:
                self.logger.error("%s", exc)
            return self._handle_item_failure(request_id, exc)
        self._tracker().success()
        return (_PROCESS_OUTPUT_MARKER, "output", serialized_result)

    def get_spawn_state(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "config": self.config,
            "runtime_context": self.runtime_context,
            "factory_module": self.factory_module,
            "factory_qualname": self.factory_qualname,
            "reports_model_class_mapping": self.reports_model_class_mapping,
            "ready_event": self.ready_event,
            "init_failed_event": self.init_failed_event,
            "error_policy": self.error_policy_state,
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
        self.source_ids: tuple[int, ...] = ()
        self.worker_count = 1
        capabilities = set(registered_module.spec.capabilities or ())
        factory = registered_module.spec.factory
        self._config: dict[str, Any] = {}
        self._input_queue: queue.Queue = queue.Queue(maxsize=8)
        self._output_queue: queue.Queue = queue.Queue(maxsize=8)
        self._pending_items = 0
        self._pending_items_lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._module = None
        self._state = None
        self._mp_control = None
        # ``degraded`` = permanent failure OR transient trouble inside the sliding window.
        self._failed = False
        self._transient_problems = RollingEventCounter()
        self.degraded = False
        self.input_queue_dropped = 0
        self.input_queue_rejected = 0
        self.item_errors = 0
        self.worker_restarts = 0
        self._error_policy = _ItemErrorPolicy()
        self._thread_error_tracker = _ItemErrorTracker(self._error_policy)
        self._thread_restart_times: list[float] = []
        self._seen_process_restarts = 0
        self._failure_reported = False
        self._thread_ready_events: list[threading.Event] = []
        self._thread_init_failed_events: list[threading.Event] = []
        self._process_ready_events: list[Any] = []
        self._process_init_failed_events: list[Any] = []
        self._model_class_mapping: dict[str, int] | None = None
        self._model_class_mapping_lock = threading.Lock()
        from ..frame_transport import SharedFrameTransport
        self._frame_transport = SharedFrameTransport()
        self._process_pending: dict[int, dict[str, Any]] = {}
        self._process_pending_lock = threading.Lock()
        self._process_sequence = 0
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

    @property
    def degraded(self) -> bool:
        return self._failed or self._transient_problems.active()

    @degraded.setter
    def degraded(self, value: bool) -> None:
        self._failed = bool(value)
        if not value:
            self._transient_problems.reset()

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
        self._error_policy = _ItemErrorPolicy.from_params(params, self.module_id)
        self._thread_error_tracker = _ItemErrorTracker(self._error_policy)
        reserved = {
            "type", "module_id", "execution_mode", "source_ids", "queue_size",
            "ipc_mode", "worker_count", "config",
        } | _ERROR_POLICY_PARAMS
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

    def _track_submitted_item(self, dropped_payload=None) -> None:
        with self._pending_items_lock:
            if dropped_payload is not None:
                self._pending_items = max(0, self._pending_items - 1)
            self._pending_items += 1

    def _track_completed_item(self) -> None:
        with self._pending_items_lock:
            self._pending_items = max(0, self._pending_items - 1)

    def _clear_pending_items(self) -> None:
        with self._pending_items_lock:
            self._pending_items = 0

    def pending_work_count(self) -> int:
        with self._pending_items_lock:
            return self._pending_items

    def has_pending_work(self) -> bool:
        return self.pending_work_count() > 0

    def _record_input_drop(self) -> None:
        self.input_queue_dropped += 1
        self._transient_problems.record()
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
                try:
                    dropped, dropped_payload = self._mp_control.put_drop_oldest(payload)
                except queue.Full as exc:
                    evicted_payload = getattr(exc, "dropped_item", None)
                    if evicted_payload is not None:
                        self._record_input_drop()
                    self._record_input_drop()
                    return _IncomingFrameDropped(evicted_payload)
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
            from ..plugins import plugin_manager

            raise PluginError(
                f"Unknown plugin module '{self.module_id}'{plugin_manager.failure_hint()}"
            )
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
        self.degraded = False
        self._reset_error_state()
        self._clear_pending_items()
        if self.execution_mode == "process":
            from ..mp_context import get_spawn_context
            from ..mp_control import MpControl

            mp_context = get_spawn_context()
            ready_event = mp_context.Event()
            init_failed_event = mp_context.Event()
            self._process_ready_events = [ready_event]
            self._process_init_failed_events = [init_failed_event]
            self._thread_ready_events = []
            self._thread_init_failed_events = []
            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Plugin-{self.module_id.replace('/', '-')}",
                **self._error_policy.mp_control_kwargs(),
            )
            worker = self._mp_control.add_worker(ItemModuleWorker)
            worker.error_policy_state = self._error_policy.to_state()
            worker.module_id = self.module_id
            worker.config = self._config
            worker.runtime_context = self._module_runtime_context()
            worker.factory_module = self.registered_module.spec.factory.__module__
            worker.factory_qualname = self.registered_module.spec.factory.__qualname__
            worker.module = None
            worker.module_state = None
            worker.drop_oldest_on_full = False
            worker.reports_model_class_mapping = self.reports_model_class_mapping
            worker.ready_event = ready_event
            worker.init_failed_event = init_failed_event
            self._mp_control.start()
            return

        self._process_ready_events = []
        self._process_init_failed_events = []
        self._thread_ready_events = [threading.Event()]
        self._thread_init_failed_events = [threading.Event()]
        self._module = None
        self._state = None
        self._thread = threading.Thread(
            target=self._run_thread,
            name=f"Plugin-{self.module_id.replace('/', '-')}",
            daemon=True,
        )
        self._thread.start()

    def _reset_error_state(self) -> None:
        self.item_errors = 0
        self.worker_restarts = 0
        self._thread_error_tracker = _ItemErrorTracker(self._error_policy)
        self._thread_restart_times = []
        self._seen_process_restarts = 0

    def _init_thread_module(self) -> None:
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

    def _restart_thread_module(self) -> bool:
        """Recreate the module after repeated failures; False when the budget is spent."""
        policy = self._error_policy
        now = time.monotonic()
        self._thread_restart_times = [
            t for t in self._thread_restart_times if now - t < policy.restart_window_s
        ]
        if len(self._thread_restart_times) >= policy.max_restarts:
            self.logger.error(
                "Plugin module %s exhausted its restart budget (%d restarts in %.0fs)",
                self.module_id, policy.max_restarts, policy.restart_window_s,
            )
            return False
        self._thread_restart_times.append(now)
        backoff = min(0.5 * (2 ** (len(self._thread_restart_times) - 1)), 5.0)
        if self._stop_event.wait(backoff):
            return False
        _close_item_resources(self._module, self._state, self.logger, self.module_id)
        self._module = None
        self._state = None
        try:
            self._init_thread_module()
        except Exception:
            self.logger.exception(
                "Plugin module %s failed to restart after repeated errors", self.module_id
            )
            return False
        self.worker_restarts += 1
        self._thread_error_tracker.success()
        self.logger.warning(
            "Plugin module %s restarted after repeated item errors (restarts=%d)",
            self.module_id, self.worker_restarts,
        )
        return True

    def _run_thread(self):
        try:
            try:
                self._init_thread_module()
            except Exception:
                self.degraded = True
                self._thread_init_failed_events[0].set()
                self.logger.exception("Plugin module %s failed during worker initialization", self.module_id)
                return

            self._thread_ready_events[0].set()
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
                    self._thread_error_tracker.success()
                    if result is not None:
                        while not self._stop_event.is_set():
                            try:
                                self._output_queue.put(result, timeout=0.1)
                                break
                            except queue.Full:
                                continue
                    else:
                        self._track_completed_item()
                except Exception:
                    self.item_errors += 1
                    action = self._thread_error_tracker.failure()
                    if self._thread_error_tracker.consecutive == 1:
                        self.logger.exception(
                            "Plugin module %s failed while processing item (policy=%s)",
                            self.module_id, self._error_policy.policy,
                        )
                    else:
                        self.logger.warning(
                            "Plugin module %s failed again while processing item "
                            "(consecutive=%d, policy=%s)",
                            self.module_id, self._thread_error_tracker.consecutive,
                            self._error_policy.policy,
                        )
                    self._track_completed_item()
                    if action == "skip":
                        continue
                    if action == "restart" and self._restart_thread_module():
                        continue
                    self.degraded = True
                    self._clear_pending_items()
                    break
        finally:
            _close_item_resources(self._module, self._state, self.logger, self.module_id)
            self._module = None
            self._state = None

    def is_ready(self, timeout: float = 30.0) -> bool:
        """Wait until every item worker has completed module initialization."""
        try:
            timeout = max(0.0, float(timeout))
        except (TypeError, ValueError) as exc:
            raise PluginError("readiness timeout must be a non-negative number") from exc

        ready_events = (
            self._process_ready_events
            if self.execution_mode == "process"
            else self._thread_ready_events
        )
        failed_events = (
            self._process_init_failed_events
            if self.execution_mode == "process"
            else self._thread_init_failed_events
        )
        if not ready_events:
            return False

        deadline = time.monotonic() + timeout
        while True:
            if self._failed:
                return False
            if any(event.is_set() for event in failed_events):
                if self.execution_mode == "process":
                    if self._mp_control is not None:
                        # Initialization errors are configuration/environment
                        # problems; restarting the worker cannot fix them.
                        self._mp_control.restart_on_exit = False
                    self.get()
                if not self.degraded:
                    self.degraded = True
                    self.logger.error(
                        "Plugin module %s worker failed during initialization",
                        self.module_id,
                    )
                return False
            if all(event.is_set() for event in ready_events):
                return True

            if self.execution_mode == "process":
                self._check_process_health()
                if self._failed:
                    return False
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            next_event = next(
                event for event in ready_events if not event.is_set()
            )
            next_event.wait(min(0.05, remaining))

    def put(self, item):
        request_id = None
        try:
            payload = item
            if self.execution_mode == "process":
                if self._mp_control is None:
                    raise RuntimeError(
                        f"Process module '{self.module_id}' is not started"
                    )
                with self._process_pending_lock:
                    request_id = self._process_sequence
                    self._process_sequence += 1
                if self.accepts_frame_handle:
                    process_item, frames, handles = _prepare_item_for_process(
                        item, self._frame_transport, request_id
                    )
                else:
                    process_item, frames, handles = item, {}, []
                try:
                    serialized_item = _serialize_process_value(
                        process_item, self.module_id, "input item"
                    )
                except Exception:
                    for handle in handles:
                        self._frame_transport.release_frame(handle)
                    raise
                with self._process_pending_lock:
                    self._process_pending[request_id] = {
                        "frames": frames, "handles": handles,
                    }
                payload = (_PROCESS_INPUT_MARKER, request_id, serialized_item)
            dropped_payload = self._enqueue_input(item, payload)
            if isinstance(dropped_payload, _IncomingFrameDropped):
                self._release_process_payload(dropped_payload.evicted_payload)
                self._release_process_request(request_id)
                if dropped_payload.evicted_payload is not None:
                    self._track_completed_item()
                return
            self._release_process_payload(dropped_payload)
            self._track_submitted_item(dropped_payload)
        except queue.Full:
            self._release_process_request(request_id)
            self.input_queue_rejected += 1
            self._transient_problems.record()
            self.logger.error("Plugin module %s input queue is full", self.module_id)
            raise RuntimeError(f"Plugin module '{self.module_id}' input queue is full")
        except PluginError as exc:
            self._release_process_request(request_id)
            self.degraded = True
            self.logger.error("%s", exc)
            raise
        except Exception:
            self._release_process_request(request_id)
            raise

    def _release_process_payload(self, payload: Any) -> None:
        request_id = _request_id_from_process_payload(payload)
        if request_id is not None:
            self._release_process_request(request_id)

    def _release_process_request(self, request_id: int | None):
        if request_id is None:
            return None
        with self._process_pending_lock:
            pending = self._process_pending.pop(request_id, None)
        if pending is not None:
            for handle in pending["handles"]:
                self._frame_transport.release_frame(handle)
        return pending

    def _release_all_process_requests(self) -> None:
        with self._process_pending_lock:
            pending = list(self._process_pending.values())
            self._process_pending.clear()
        for request in pending:
            for handle in request["handles"]:
                self._frame_transport.release_frame(handle)

    def get(self):
        self._check_process_health()
        try:
            if self.execution_mode == "process":
                if self._mp_control is None:
                    return None
                while True:
                    result = self._mp_control.get_nowait()
                    if not (
                        isinstance(result, tuple) and len(result) == 3
                        and result[0] == _PROCESS_OUTPUT_MARKER
                    ):
                        self.degraded = True
                        self._release_all_process_requests()
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
                    if result[1] == "item_error":
                        request_id, message = None, result[2]
                        if isinstance(message, bytes):
                            try:
                                request_id, message = pickle.loads(message)
                            except Exception:
                                pass
                        self._release_process_request(request_id)
                        self._track_completed_item()
                        self.item_errors += 1
                        self.logger.warning(
                            "Plugin module %s skipped an item after an error: %s",
                            self.module_id, message,
                        )
                        continue
                    if result[1] == "error":
                        request_id = None
                        message = result[2]
                        if isinstance(message, bytes):
                            try:
                                request_id, message = pickle.loads(message)
                            except Exception:
                                pass
                        self._release_process_request(request_id)
                        self._release_all_process_requests()
                        self.degraded = True
                        self._failure_reported = True
                        self._clear_pending_items()
                        self.logger.error(
                            "Plugin module %s failed in worker: %s", self.module_id, message
                        )
                        return None
                    if result[1] == "skip":
                        self._release_process_request(
                            result[2] if isinstance(result[2], int) else None
                        )
                        self._track_completed_item()
                        continue
                    if result[1] == "output":
                        self._track_completed_item()
                        request_id = None
                        try:
                            decoded = pickle.loads(result[2])
                            if (
                                isinstance(decoded, tuple) and len(decoded) == 3
                                and decoded[0] == _PROCESS_RESULT_MARKER
                                and isinstance(decoded[1], int)
                            ):
                                request_id = decoded[1]
                                pending = self._process_pending.get(request_id)
                                if pending is None:
                                    raise PluginError(
                                        f"Module '{self.module_id}' returned an unknown "
                                        f"process request id {request_id}"
                                    )
                                output = _restore_process_result(
                                    decoded[2], pending["frames"], request_id
                                )
                                self._release_process_request(request_id)
                                return output
                            raise PluginError(
                                f"Module '{self.module_id}' returned an invalid "
                                "process result envelope"
                            )
                        except Exception as exc:
                            self._release_process_request(request_id)
                            self._release_all_process_requests()
                            self.degraded = True
                            self.logger.error(
                                "Plugin module %s returned an invalid serialized output: %s",
                                self.module_id,
                                exc,
                            )
                            return None
                    self.degraded = True
                    self._release_all_process_requests()
                    self.logger.error(
                        "Plugin module %s returned an unknown process envelope",
                        self.module_id,
                    )
                    return None
            result = self._output_queue.get_nowait()
            self._track_completed_item()
            return result
        except queue.Empty:
            self._check_process_health()
            return None
        except Exception as exc:
            if exc.__class__.__name__ == "Empty":
                self._check_process_health()
                return None
            raise

    def _on_workers_restarted(self) -> None:
        """Hook: a pool restart discarded all in-flight work."""

    def _check_process_health(self):
        if (
            self._mp_control is None
            or self._stop_event.is_set()
            or self._failure_reported
            or any(event.is_set() for event in self._process_init_failed_events)
        ):
            return
        restart_count = getattr(self._mp_control, "restart_count", None)
        restarts = restart_count() if callable(restart_count) else 0
        if restarts != self._seen_process_restarts:
            # A restarted worker drops everything queued for its predecessor.
            self.worker_restarts += restarts - self._seen_process_restarts
            self._seen_process_restarts = restarts
            self._release_all_process_requests()
            self._clear_pending_items()
            self._on_workers_restarted()
        is_final = getattr(
            self._mp_control, "worker_exit_is_final",
            lambda process: process.exitcode is not None,
        )
        exited = [p for p in self._mp_control.processes if is_final(p)]
        if exited:
            self.degraded = True
            self._failure_reported = True
            self._release_all_process_requests()
            self._clear_pending_items()
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
            "in_flight": self.pending_work_count(),
            "degraded": self.degraded,
            "error_policy": self._error_policy.policy,
            "item_errors": self.item_errors,
            "worker_restarts": self.worker_restarts,
            "failed": self._failed,
            "recent_overload_events": self._transient_problems.recent(),
            "degraded_window_sec": self._transient_problems.window_sec,
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
        self._release_all_process_requests()
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
        self._reset_error_state()
        self._failure_reported = False
        self._clear_pending_items()
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
