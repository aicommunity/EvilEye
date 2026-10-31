"""Event detector adapter and its process worker."""

from __future__ import annotations

import importlib
import pickle
import queue
import threading
import time
from typing import Any, Mapping

from ..base_class import EvilEyeBase
from ..contracts import EventFrameSnapshot, EventUpdate
from ..mp_worker import MpWorker
from ..plugins import ModuleRuntimeContext, PluginError, plugin_registry
from .policy import (
    _ERROR_POLICY_PARAMS,
    _HealthMixin,
    _ItemErrorPolicy,
    _ItemErrorTracker,
)
from .transport import _call_factory, _close_item_resources, _create_state, _serialize_process_value

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
            self._tracker().success()
            return (_EVENT_UPDATE_OUTPUT, "output", payload)
        except Exception as exc:
            if self.logger:
                self.logger.exception(
                    "Event detector %s failed while processing update", self.module_id
                )
            action = self._tracker().failure()
            if action != "skip":
                # restart: the worker exits and MpControl starts a fresh one; fail: stay down.
                self._stop_event.set()
            kind = "error" if action == "fail" else "item_error"
            return (_EVENT_UPDATE_OUTPUT, kind, str(exc))

    def get_spawn_state(self) -> dict[str, Any]:
        return {
            "module_id": self.module_id,
            "config": self.config,
            "factory_module": self.factory_module,
            "factory_qualname": self.factory_qualname,
            "error_policy": self.error_policy_state,
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


class EventDetectorModuleAdapter(_HealthMixin, EvilEyeBase):
    """Own event-detector construction, config, and thread/process lifecycle."""

    def __init__(self, registered_module, context):
        self.registered_module = registered_module
        self.module_id = registered_module.qualified_id
        self.context = context
        self.module = None
        self._config: dict[str, Any] = {}
        self._started = False
        self.execution_mode = "thread"
        # Event detectors keep state (open events), so a restart loses it: the default
        # stays ``fail_stop``; ``skip_item``/``restart`` must be requested explicitly.
        self._error_policy = _ItemErrorPolicy(policy="fail_stop")
        self.item_errors = 0
        self.worker_restarts = 0
        self._seen_process_restarts = 0
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
        self._sequence_lock = threading.Lock()
        self._updates_submitted = 0
        self._events_received = 0
        self._updates_completed = 0
        self._last_success_at = None
        self._started_at = None
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
                {"event_updates", "source_updates", "event_commands"}
            )
            if not input_capabilities:
                raise PluginError(
                    f"Process event detector '{self.module_id}' must declare "
                    "event_updates, source_updates or event_commands"
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
        if "event_frames" in capabilities and "event_updates" not in capabilities:
            raise PluginError(
                f"Process event detector '{self.module_id}' must declare event_updates "
                "when it requests event_frames"
            )
        reserved = {
            "module_id", "type", "execution_mode", "logger_name",
            "queue_size", "config",
        } | _ERROR_POLICY_PARAMS
        self._error_policy = _ItemErrorPolicy.from_params(
            params, self.module_id, default_policy="fail_stop"
        )
        self._set_degraded_threshold(self._error_policy.degraded_threshold)
        config = params.get("config")
        if config is None:
            config = {key: value for key, value in params.items() if key not in reserved}
        if not isinstance(config, dict):
            raise PluginError(f"Event detector '{self.module_id}' config must be an object")
        self._config = dict(config)
        self._queue_size = max(1, int(params.get("queue_size", 32)))
        if requested_mode == "process" and "event_frames" in capabilities:
            if self._queue_size > 4:
                self.logger.info(
                    "Capping event frame worker queue for %s from %d to 4",
                    self.module_id,
                    self._queue_size,
                )
                self._queue_size = 4
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
        self._started_at = time.time()
        if self.execution_mode == "process":
            from ..mp_control import MpControl

            self._mp_control = MpControl(
                max_input_size=self._queue_size,
                max_output_size=self._queue_size,
                name=f"Event-{self.module_id.replace('/', '-')}",
                **self._error_policy.mp_control_kwargs(),
            )
            self._seen_process_restarts = 0
            worker = self._mp_control.add_worker(EventDetectorUpdateWorker)
            worker.error_policy_state = self._error_policy.to_state()
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
            if set(self.registered_module.spec.capabilities).intersection(
                {"event_updates", "source_updates"}
            ):
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

    def _snapshot_event_frame_ref(
        self,
        frame: Any,
        source_id: int | None,
        frames: list[EventFrameSnapshot],
        frame_indices: dict[tuple[Any, ...], int],
    ) -> int | None:
        if frame is None:
            return None
        image = getattr(frame, "image", None)
        if image is None:
            return None
        frame_source_id = getattr(frame, "source_id", None)
        if frame_source_id is None:
            frame_source_id = source_id
        frame_source_id = self._snapshot_value(frame_source_id)
        if not isinstance(frame_source_id, int) or isinstance(frame_source_id, bool):
            raise PluginError(
                f"Event detector '{self.module_id}' frame source_id must be an integer"
            )
        frame_id = self._snapshot_value(getattr(frame, "frame_id", None))
        if frame_id is not None:
            try:
                frame_id = int(frame_id)
            except (TypeError, ValueError) as exc:
                raise PluginError(
                    f"Event detector '{self.module_id}' frame_id must be an integer"
                ) from exc
            key = (frame_source_id, frame_id, id(image))
        else:
            key = (frame_source_id, None, id(image))
        existing_index = frame_indices.get(key)
        if existing_index is not None:
            return existing_index

        try:
            import cv2
            import numpy as np

            ok, encoded = cv2.imencode(
                ".jpg",
                image,
                [int(cv2.IMWRITE_JPEG_QUALITY), 85],
            )
        except Exception as exc:
            raise PluginError(
                f"Event detector '{self.module_id}' could not encode frame {frame_id}: {exc}"
            ) from exc
        if not ok:
            raise PluginError(
                f"Event detector '{self.module_id}' could not encode frame {frame_id}"
            )
        jpeg_bytes = np.asarray(encoded).tobytes()
        snapshot = EventFrameSnapshot(
            source_id=frame_source_id,
            frame_id=frame_id,
            timestamp=self._snapshot_value(getattr(frame, "time_stamp", None)),
            current_video_position=self._snapshot_value(
                getattr(frame, "current_video_position", None)
            ),
            jpeg_bytes=jpeg_bytes,
        )
        frame_index = len(frames)
        frames.append(snapshot)
        frame_indices[key] = frame_index
        return frame_index

    def _snapshot_object(
        self,
        obj: Any,
        *,
        frame_store: list[EventFrameSnapshot] | None = None,
        frame_indices: dict[tuple[Any, ...], int] | None = None,
        source_id: int | None = None,
    ) -> dict[str, Any]:
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
                "time_detected": self._snapshot_value(getattr(value, "time_detected", None)),
                "time_lost": self._snapshot_value(getattr(value, "time_lost", None)),
                "bbox": self._snapshot_value(bbox) if bbox is not None else None,
            }

        track = getattr(obj, "track", None)
        bbox = getattr(track, "bounding_box", None) if track is not None else None
        history = getattr(obj, "history", ()) or ()
        snapshot = {
            "object_id": self._snapshot_value(getattr(obj, "object_id", None)),
            "global_id": self._snapshot_value(getattr(obj, "global_id", None)),
            "source_id": self._snapshot_value(
                getattr(obj, "source_id", None)
                if getattr(obj, "source_id", None) is not None
                else source_id
            ),
            "class_id": self._snapshot_value(getattr(obj, "class_id", None)),
            "frame_id": self._snapshot_value(getattr(obj, "frame_id", None)),
            "timestamp": self._snapshot_value(getattr(obj, "time_stamp", None)),
            "time_detected": self._snapshot_value(getattr(obj, "time_detected", None)),
            "time_lost": self._snapshot_value(getattr(obj, "time_lost", None)),
            "bbox": self._snapshot_value(bbox) if bbox is not None else None,
            "attributes": self._snapshot_value(getattr(obj, "attributes", {}) or {}),
            "history": [_entry(item) for item in history],
        }
        if frame_store is not None and frame_indices is not None:
            object_source_id = snapshot["source_id"]
            last_image = getattr(obj, "last_image", None)
            snapshot["last_image_ref"] = self._snapshot_event_frame_ref(
                last_image, object_source_id, frame_store, frame_indices
            )
            sticky_image = getattr(obj, "_zone_event_sticky_image", None)
            snapshot["zone_sticky_image_ref"] = self._snapshot_event_frame_ref(
                sticky_image, object_source_id, frame_store, frame_indices
            )
        return snapshot

    def _next_event_sequence(self) -> int:
        with self._sequence_lock:
            sequence = self._sequence
            self._sequence += 1
            return sequence

    def _build_context_updates(self) -> list[EventUpdate]:
        import datetime

        capabilities = set(self.registered_module.spec.capabilities)
        updates = []
        if "event_updates" in capabilities:
            handler = getattr(self.context, "objects_handler", None)
            if handler is None:
                raise PluginError(
                    f"Process event detector '{self.module_id}' requires objects_handler "
                    "to build event_updates"
                )
            include_frames = "event_frames" in capabilities
            for source_id in self.context.pipeline_source_ids:
                active = handler.get("active", source_id)
                lost = handler.get("lost", source_id)
                active_objects = getattr(active, "objects", ()) if active is not None else ()
                lost_objects = getattr(lost, "objects", ()) if lost is not None else ()
                frame_store: list[EventFrameSnapshot] = []
                frame_indices: dict[tuple[Any, ...], int] = {}
                object_snapshot_args = (
                    {
                        "frame_store": frame_store,
                        "frame_indices": frame_indices,
                        "source_id": int(source_id),
                    }
                    if include_frames else {}
                )
                update = EventUpdate(
                    sequence=self._next_event_sequence(),
                    kind="object_snapshot",
                    source_id=int(source_id),
                    timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    payload={
                        "active": [
                            self._snapshot_object(obj, **object_snapshot_args)
                            for obj in active_objects
                        ],
                        "lost": [
                            self._snapshot_object(obj, **object_snapshot_args)
                            for obj in lost_objects
                        ],
                    },
                    frames=tuple(frame_store),
                )
                updates.append(update)

        if "source_updates" in capabilities:
            for source_index, source in enumerate(self.context.sources):
                disconnects = source.get_disconnects_info()
                reconnects = source.get_reconnects_info()
                if not disconnects and not reconnects:
                    continue

                def _transition(item):
                    address, timestamp, is_connected = item
                    return {
                        "address": str(address),
                        "timestamp": self._snapshot_value(timestamp),
                        "is_connected": bool(is_connected),
                    }

                updates.append(
                    EventUpdate(
                        sequence=self._next_event_sequence(),
                        kind="source_status",
                        source_id=source_index,
                        timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                        payload={
                            "disconnects": [_transition(item) for item in disconnects],
                            "reconnects": [_transition(item) for item in reconnects],
                        },
                    )
                )
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

    def submit_command(self, command: str, *, config_patch=None, **kwargs):
        """Submit a named module command through the detector execution boundary."""
        command = str(command).strip()
        if not command:
            raise PluginError(f"Event detector '{self.module_id}' command must not be empty")
        if self.execution_mode != "process":
            result = self._call_module(command, **kwargs)
        else:
            if "event_commands" not in self.registered_module.spec.capabilities:
                raise PluginError(
                    f"Process event detector '{self.module_id}' does not accept module commands"
                )
            import datetime

            update = EventUpdate(
                sequence=self._next_event_sequence(),
                kind="module_command",
                timestamp=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                payload={
                    "command": command,
                    "kwargs": self._snapshot_value(kwargs),
                },
            )
            result = self.put(update)
        if config_patch is not None:
            if not isinstance(config_patch, Mapping):
                raise PluginError("Event detector config_patch must be a mapping")
            self._config.update(self._snapshot_value(config_patch))
        return result

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
            if envelope[1] == "item_error":
                self.item_errors += 1
                self._record_item_error_event()
                self.logger.warning(
                    "Event detector %s skipped an update after an error: %s",
                    self.module_id, envelope[2],
                )
                continue
            if envelope[1] == "ready":
                # A restarted worker announces itself again; the first one is consumed in start().
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
                self._events_received += len(pickle.loads(envelope[2]))
                self._updates_completed += 1
                self._last_success_at = time.time()
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
        if (
            self._mp_control is None
            or not self._started
            or self._closing
            or self._failure_reported
        ):
            return
        restart_count = getattr(self._mp_control, "restart_count", None)
        restarts = restart_count() if callable(restart_count) else 0
        if restarts != self._seen_process_restarts:
            self.worker_restarts += restarts - self._seen_process_restarts
            self._transient_problems.record(restarts - self._seen_process_restarts)
            self._seen_process_restarts = restarts
            self.logger.warning(
                "Event detector %s worker was restarted (restarts=%d)",
                self.module_id, self.worker_restarts,
            )
        is_final = getattr(
            self._mp_control, "worker_exit_is_final",
            lambda process: process.exitcode is not None,
        )
        exited = [p for p in self._mp_control.processes if is_final(p)]
        if exited:
            self._failure_reported = True
            self._record_failure(
                "worker exit",
                RuntimeError(f"worker exited unexpectedly with code {exited[0].exitcode}"),
            )

    def update(self):
        if self.execution_mode == "process":
            if not set(self.registered_module.spec.capabilities).intersection(
                {"event_updates", "source_updates"}
            ):
                raise PluginError(
                    f"Process event detector '{self.module_id}' does not accept "
                    "host update notifications"
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
            sequence=self._next_event_sequence(),
            kind="system_message",
            timestamp=datetime.datetime.now().isoformat(),
            payload={
                "event_type": str(event_type),
                "message": str(message),
            },
        )
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
            thread = getattr(self.module, "processing_thread", None)
            worker_running = bool(self._started and (thread is None or thread.is_alive()))
        else:
            module_stats = None
        return {
            "module_id": self.module_id,
            "execution_mode": self.execution_mode,
            "initialized": self.is_inited,
            "started": self._started,
            "worker_running": worker_running,
            "started_at": self._started_at,
            "last_success_at": self._last_success_at,
            "updates_completed": self._updates_completed,
            "updates_submitted": self._updates_submitted,
            "update_notifications_dropped": self._notifications_dropped,
            "process_updates_dropped": self._process_updates_dropped,
            "events_received": self._events_received,
            "degraded": self.degraded,
            "last_error": self.last_error,
            "error_policy": self._error_policy.policy,
            "item_errors": self.item_errors,
            "worker_restarts": self.worker_restarts,
            **self._health_stats(),
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
        self.item_errors = 0
        self.worker_restarts = 0
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
