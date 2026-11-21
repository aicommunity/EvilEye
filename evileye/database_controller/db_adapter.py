from __future__ import annotations

import datetime
import os
from typing import Any, Optional, Dict
from ..core.base_class import EvilEyeBase
from ..core.interfaces import IDatabaseAdapter
from .database_controller_pg import DatabaseControllerPg
from .database_error_handler import DatabaseErrorHandler
import time
from threading import Lock, Thread, current_thread
from queue import Queue, Empty
from abc import abstractmethod, ABC


def _spool_value_supported(value: Any) -> bool:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return True
    if isinstance(value, (datetime.datetime, datetime.date)):
        return True
    if isinstance(value, dict):
        return all(_spool_value_supported(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(_spool_value_supported(item) for item in value)
    return False


def _spool_event_class(event_type: str):
    if not event_type or event_type == "dict":
        return None
    from evileye.events_detectors.alarm_event import AlarmEvent
    from evileye.events_detectors.event_attribute import AttributeEvent
    from evileye.events_detectors.event_cameras import CameraEvent
    from evileye.events_detectors.event_schedule_alarm import ScheduleAlarmEvent
    from evileye.events_detectors.event_system import SystemEvent
    from evileye.events_detectors.event_zone import ZoneEvent

    return {
        "ZoneEvent": ZoneEvent,
        "ScheduleAlarmEvent": ScheduleAlarmEvent,
        "AttributeEvent": AttributeEvent,
        "CameraEvent": CameraEvent,
        "SystemEvent": SystemEvent,
        "AlarmEvent": AlarmEvent,
    }.get(event_type)


class DatabaseAdapterBase(EvilEyeBase, ABC):
    # Distinguishes PostgreSQL adapters from JSON journal adapters in shared
    # code paths (table-name collection, spooling). Audit 2026-11 (D2).
    storage_backend: str = "postgres"

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
        # Local spool for items that exhaust the retry budget (audit A5).
        # Only PostgreSQL adapters spill to disk; the JSON journal is already
        # file-based.
        self._spool = None
        self._spooled_items = 0
        self._replayed_items = 0
        self._consecutive_write_failures = 0

    def _ensure_spool(self):
        if self._spool is not None:
            return self._spool
        if self.storage_backend != "postgres":
            return None
        from .pg_spool import PgSpool

        image_dir = "EvilEyeData"
        try:
            image_dir = str(self.db_params.get("image_dir") or image_dir)
        except Exception:
            pass
        namespace = self.event_name or self.__class__.__name__
        self._spool = PgSpool(image_dir, namespace=namespace, logger=self.logger)
        return self._spool

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

    def _postgres_disconnected(self) -> bool:
        """True only for PostgreSQL adapters whose controller reports no connection.

        JSON journals must keep writing while PostgreSQL is down. They do not
        consult ``is_connected`` and they do not spill into ``pg_spool``.
        """
        if self.storage_backend != "postgres":
            return False
        controller = self.db_controller
        if controller is None or not hasattr(controller, "is_connected"):
            return False
        return not controller.is_connected()

    def _reject_if_closing(self, operation: str) -> None:
        if self._closing:
            exc = RuntimeError(
                "Database adapter worker is not running because the adapter is stopping"
            )
            self._record_failure(operation, exc, category="enqueue")
            raise exc

    def insert(self, data: Any) -> None:
        if self._postgres_disconnected():
            # Audit A5: defer to the local spool instead of losing the
            # event (previously: ConnectionError after 3 retries).
            if self._spool_deferred("insert", data):
                return
            exc = ConnectionError(f"Database adapter '{self.event_name}' is disconnected")
            self._record_failure('insert', exc, category='enqueue')
            raise exc
        # Serialize acceptance with stop(): work accepted before shutdown is drained,
        # and work arriving after shutdown is explicitly rejected.
        with self._lifecycle_lock:
            self._reject_if_closing("insert")
            self._insert_impl(data)

    def update(self, data: Any) -> None:
        if self._postgres_disconnected():
            # Audit A5: defer to the local spool instead of losing the event update.
            if self._spool_deferred("update", data):
                return
            exc = ConnectionError(f"Database adapter '{self.event_name}' is disconnected")
            self._record_failure('update', exc, category='enqueue')
            raise exc
        with self._lifecycle_lock:
            self._reject_if_closing("update")
            self._update_impl(data)

    def _spool_deferred(self, operation: str, event: Any) -> bool:
        """Spool an event accepted while the database is disconnected."""
        spool = self._ensure_spool()
        if spool is None:
            return False
        record = self._deferred_spool_record(operation, event)
        if record is not None and spool.append(record):
            self._spooled_items += 1
            self.degraded = True
            self.last_error = (
                f"{operation} deferred to pg_spool (database disconnected); "
                f"spooled={self._spooled_items}"
            )
            self.logger.warning(
                "Database adapter '%s' %s deferred to spool (database disconnected)",
                self.event_name,
                operation,
            )
            return True
        return False

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
            "spooled_items": self._spooled_items,
            "replayed_items": self._replayed_items,
        }

    def _execute_query(self) -> None:
        """Retry transient writes; spool items that cannot be saved (audit A5)."""
        while self.run_flag or not self.queue_in.empty():
            try:
                item = self.queue_in.get(timeout=0.1)
            except Empty:
                if self.run_flag and self._spool_has_pending():
                    self._try_replay_spool()
                continue
            _, error = self.error_handler.execute_with_retry(
                lambda: self._process_queue_item(item),
                max_retries=3,
                initial_delay=0.1,
                max_delay=0.5,
            )
            if error is not None:
                self._record_failure('queued write', error, category='terminal_write')
                self._consecutive_write_failures += 1
                record = self._queue_item_spool_record(item)
                spool = self._ensure_spool()
                if record is not None and spool is not None and spool.append(record):
                    self._spooled_items += 1
                elif spool is not None and spool.last_reject == "io":
                    try:
                        self.queue_in.put_nowait(item)
                    except Exception:
                        pass
            else:
                self.processed_items += 1
                if self._consecutive_write_failures or self._spool_has_pending():
                    self._try_replay_spool()
                    if not self._spool_has_pending():
                        self._consecutive_write_failures = 0

    def _try_replay_spool(self) -> None:
        spool = self._ensure_spool()
        if spool is None:
            return
        try:
            pending = spool.pending_count()
        except Exception:
            return
        if not pending:
            return
        replayed = spool.replay(self._replay_spool_item)
        if replayed:
            self._replayed_items += replayed
            self.processed_items += replayed
            self.logger.info(
                "Database adapter '%s' replayed %d spooled items (%d pending)",
                self.event_name,
                replayed,
                spool.pending_count(),
            )

    def _spool_has_pending(self) -> bool:
        spool = self._ensure_spool()
        if spool is None:
            return False
        try:
            return spool.pending_count() > 0
        except Exception:
            return False

    def _replay_spool_item(self, item: Any) -> None:
        if isinstance(item, dict) and item.get("kind") == "deferred":
            event = self._event_from_spool_record(item)
            if item.get("op") == "insert":
                self._insert_impl(event)
            else:
                self._update_impl(event)
            return
        if isinstance(item, dict) and item.get("kind") == "sql":
            self._process_queue_item(self._queue_item_from_spool_record(item))
            return
        raise ValueError("unsupported spool record")

    def _deferred_spool_record(self, operation: str, event: Any) -> Optional[dict[str, Any]]:
        fields, images = self._spool_event_payload(event)
        return {
            "v": 1,
            "kind": "deferred",
            "adapter": self.event_name,
            "op": operation,
            "event_type": "dict" if isinstance(event, dict) else type(event).__name__,
            "fields": fields,
            "images": images,
        }

    def _spool_event_payload(self, event: Any) -> tuple[dict[str, Any], dict[str, str]]:
        if isinstance(event, dict):
            return self._json_ready(event), {}
        fields: dict[str, Any] = {}
        images: dict[str, str] = {}
        for name, value in vars(event).items():
            image = self._ndarray_of(value)
            if image is not None:
                stored = self._write_spool_jpeg(name, image)
                if stored:
                    images[name] = stored
                continue
            if not _spool_value_supported(value):
                continue
            fields[name] = self._json_ready(value)
        return fields, images

    def _ndarray_of(self, value: Any):
        image = getattr(value, "image", None)
        if image is not None and hasattr(image, "shape"):
            return image
        if hasattr(value, "shape") and hasattr(value, "dtype"):
            return value
        return None

    def _write_spool_jpeg(self, name: str, image: Any) -> Optional[str]:
        spool = self._ensure_spool()
        if spool is None:
            return None
        try:
            import cv2
        except Exception:
            return None
        ok, encoded = cv2.imencode(".jpg", image)
        if not ok:
            return None
        blob_dir = spool.root / "blobs"
        blob_dir.mkdir(parents=True, exist_ok=True)
        filename = f"{time.time_ns()}-{name}.jpg"
        path = blob_dir / filename
        path.write_bytes(encoded.tobytes())
        return f"blobs/{filename}"

    def _json_ready(self, value: Any) -> Any:
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        if isinstance(value, datetime.datetime):
            return {"__dt": value.isoformat()}
        if isinstance(value, datetime.date):
            return {"__date": value.isoformat()}
        adapted = getattr(value, "adapted", None)
        if adapted is not None and adapted is not value:
            return self._json_ready(adapted)
        if isinstance(value, dict):
            return {str(key): self._json_ready(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._json_ready(item) for item in value]
        return None

    def _restore_json(self, value: Any) -> Any:
        if isinstance(value, dict) and set(value) == {"__dt"}:
            return datetime.datetime.fromisoformat(value["__dt"])
        if isinstance(value, dict) and set(value) == {"__date"}:
            return datetime.date.fromisoformat(value["__date"])
        if isinstance(value, dict):
            return {key: self._restore_json(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._restore_json(item) for item in value]
        return value

    def _event_from_spool_record(self, record: dict[str, Any]) -> Any:
        fields = self._restore_json(record.get("fields") or {})
        if record.get("event_type") == "dict":
            return fields
        event_type = str(record.get("event_type") or "")
        cls = _spool_event_class(event_type)
        if cls is None:
            raise ValueError(f"unknown spooled event type {event_type}")
        event = object.__new__(cls)
        for name, value in fields.items():
            setattr(event, name, value)
        for name, relative in (record.get("images") or {}).items():
            setattr(event, name, self._load_spool_image(str(relative)))
        return event

    def _load_spool_image(self, relative: str):
        spool = self._ensure_spool()
        if spool is None:
            return None
        path = spool.root / relative
        try:
            import cv2
        except Exception:
            return None
        image = cv2.imread(str(path), cv2.IMREAD_COLOR)
        return type("SpoolFrame", (), {"image": image})()

    def _sql_text(self, query: Any) -> Optional[str]:
        if isinstance(query, str):
            return query
        pool = getattr(self.db_controller, "conn_pool", None)
        if pool is None or not hasattr(query, "as_string"):
            return None
        connection = pool.getconn()
        try:
            return query.as_string(connection)
        except Exception:
            return None
        finally:
            try:
                pool.putconn(connection)
            except Exception:
                pass

    def _queue_item_spool_record(self, item: Any) -> Optional[dict[str, Any]]:
        if not isinstance(item, tuple):
            return None
        if len(item) == 6:
            query_type, query, data, preview_path, frame_path, image = item
            sql_text = self._sql_text(query)
            if not sql_text:
                return None
            image_file = None
            pixels = self._ndarray_of(image)
            if pixels is not None:
                image_file = self._write_spool_jpeg("frame", pixels)
            return {
                "v": 1,
                "kind": "sql",
                "adapter": self.event_name,
                "shape": "event",
                "query_type": str(query_type),
                "sql": sql_text,
                "params": self._redact_params(self._json_ready(list(data))),
                "preview_path": preview_path,
                "frame_path": frame_path,
                "image_file": image_file,
            }
        if len(item) == 2:
            query, data = item
            sql_text = self._sql_text(query)
            if not sql_text:
                return None
            return {
                "v": 1,
                "kind": "sql",
                "adapter": self.event_name,
                "shape": "simple",
                "sql": sql_text,
                "params": self._redact_params(self._json_ready(list(data))),
            }
        return None

    def _redact_params(self, params: Any) -> Any:
        if not isinstance(params, list):
            return params
        from evileye.utils.camera_event_label import media_url_without_credentials

        redacted = []
        for value in params:
            if isinstance(value, str) and "://" in value and "@" in value:
                redacted.append(media_url_without_credentials(value))
            else:
                redacted.append(value)
        return redacted

    def _queue_item_from_spool_record(self, record: dict[str, Any]):
        params = self._restore_json(record.get("params") or [])
        if record.get("shape") == "simple":
            return (record.get("sql"), params)
        image = None
        if record.get("image_file"):
            image = self._load_spool_image(str(record["image_file"]))
        return (
            record.get("query_type"),
            record.get("sql"),
            params,
            record.get("preview_path"),
            record.get("frame_path"),
            image,
        )

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
