"""Ordered multi-worker execution of parallel-safe item processors."""

from __future__ import annotations

import pickle
import queue
import threading
from typing import Any

from ..plugins import PluginError
from .item import ItemModuleAdapter, ItemModuleWorker, _ItemErrorTracker
from .transport import (
    _IncomingFrameDropped,
    _PROCESS_INPUT_MARKER,
    _PROCESS_OUTPUT_MARKER,
    _call_factory,
    _close_item_resources,
    _create_state,
    _get_model_class_mapping,
    _serialize_process_value,
    _validate_model_class_mapping_capability,
)

_ORDERED_THREAD_OUTPUT_MARKER = "__evileye_parallel_item_runtime__"


_ORDERED_SKIP = object()


_ORDERED_EVICTED = object()


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
                self._tracker().success()
                return (_PROCESS_OUTPUT_MARKER, "skip", sequence, None)
            payload = _serialize_process_value(
                result, self.module_id, "process_item result"
            )
            self._tracker().success()
            return (_PROCESS_OUTPUT_MARKER, "output", sequence, payload)
        except Exception as exc:
            if self.logger:
                self.logger.exception(
                    "Plugin module %s failed while processing ordered item %s",
                    self.module_id,
                    sequence,
                )
            if self._tracker().failure() != "skip":
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
        self.degraded = False
        self._reset_error_state()
        self._clear_pending_items()
        if self.execution_mode == "process":
            from ..mp_context import get_spawn_context
            from ..mp_control import MpControl

            mp_context = get_spawn_context()
            self._process_ready_events = []
            self._process_init_failed_events = []
            self._thread_ready_events = []
            self._thread_init_failed_events = []
            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Plugin-{self.module_id.replace('/', '-')}Pool",
                **self._error_policy.mp_control_kwargs(),
            )
            for _ in range(self.worker_count):
                worker = self._mp_control.add_worker(OrderedItemModuleWorker)
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
                worker.ready_event = mp_context.Event()
                worker.init_failed_event = mp_context.Event()
                self._process_ready_events.append(worker.ready_event)
                self._process_init_failed_events.append(worker.init_failed_event)
            self._mp_control.start()
            return

        self._process_ready_events = []
        self._process_init_failed_events = []
        self._thread_ready_events = [
            threading.Event() for _ in range(self.worker_count)
        ]
        self._thread_init_failed_events = [
            threading.Event() for _ in range(self.worker_count)
        ]
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
                self._clear_pending_items()
                self.logger.exception(
                    "Plugin module %s worker %s failed during initialization",
                    self.module_id,
                    worker_index,
                )
                self._thread_init_failed_events[worker_index].set()
                self._output_queue.put(
                    (_ORDERED_THREAD_OUTPUT_MARKER, "error", str(exc))
                )
                return

            self._thread_ready_events[worker_index].set()
            tracker = _ItemErrorTracker(self._error_policy)
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
                    tracker.success()
                    if result is None:
                        envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "skip", sequence, None)
                    else:
                        envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "output", sequence, result)
                except Exception as exc:
                    self.logger.exception(
                        "Plugin module %s worker %s failed on item %s",
                        self.module_id,
                        worker_index,
                        sequence,
                    )
                    envelope = (_ORDERED_THREAD_OUTPUT_MARKER, "error", sequence, str(exc))
                    if tracker.failure() != "skip":
                        # In-process pools do not restart workers: escalate to a stop.
                        self.degraded = True
                        self._clear_pending_items()
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
            if isinstance(dropped_payload, _IncomingFrameDropped):
                if dropped_payload.evicted_payload is not None:
                    self._track_completed_item()
                    dropped_sequence = (
                        int(dropped_payload.evicted_payload[1])
                        if self.execution_mode == "process"
                        else int(dropped_payload.evicted_payload[0])
                    )
                    self._ordered_results[dropped_sequence] = _ORDERED_EVICTED
                return
            self._track_submitted_item(dropped_payload)
            self._next_input_sequence += 1
            if dropped_payload is not None:
                dropped_sequence = (
                    int(dropped_payload[1])
                    if self.execution_mode == "process"
                    else int(dropped_payload[0])
                )
                self._ordered_results[dropped_sequence] = _ORDERED_EVICTED
        except queue.Full:
            self.input_queue_rejected += 1
            self._transient_problems.record()
            self.logger.error("Plugin module %s input queue is full", self.module_id)
            raise RuntimeError(f"Plugin module '{self.module_id}' input queue is full")
        except PluginError as exc:
            self.degraded = True
            self.logger.error("%s", exc)
            raise

    def _on_workers_restarted(self) -> None:
        # Sequences in flight at restart time never come back; do not wait for them.
        self._ordered_results.clear()
        self._next_output_sequence = self._next_input_sequence

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
            if value is _ORDERED_EVICTED:
                continue
            if value is _ORDERED_SKIP:
                self._track_completed_item()
                continue
            if isinstance(value, tuple) and len(value) == 2 and value[0] == "error":
                self.item_errors += 1
                if self._error_policy.policy != "fail_stop":
                    self._track_completed_item()
                    self.logger.warning(
                        "Plugin module %s skipped an ordered item after an error: %s",
                        self.module_id, value[1],
                    )
                    continue
                self.degraded = True
                self._clear_pending_items()
                self.logger.error("Plugin module %s failed on ordered item: %s", self.module_id, value[1])
                return None
            self._track_completed_item()
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
