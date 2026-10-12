from threading import Thread, RLock
from queue import Queue
import time
import copy
from queue import Empty, Full
from ..core.base_class import EvilEyeBase


class EventsDetectorsController(EvilEyeBase):
    def __init__(self, events_detectors: list):
        super().__init__()
        self.control_thread = Thread(target=self.run)
        self.queue_out_maxsize = 32
        self.queue_out = Queue(maxsize=self.queue_out_maxsize)
        self.detectors = events_detectors
        self.run_flag = False

        self.params = None
        self.events_detectors = {}  # Словарь, содержащий события, распределенные по детекторам

        self.any_events = False
        self._queue_drops = 0
        self._events_published = 0
        self.degraded = False
        self.last_error = None
        self._controller_degraded = False
        self._controller_last_error = None
        self._detector_failures: dict[str, str] = {}
        self._runtime_lock = RLock()

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

    def get_debug_info(self, debug_info: dict | None = None):
        if debug_info is None:
            debug_info = {}
        super().get_debug_info(debug_info)
        debug_info["runtime"] = self.get_runtime_stats()
        return debug_info

    def init_impl(self):
        self.events_detectors = {detector.get_name(): [] for detector in self.detectors}
        return True

    def start(self):
        if self.run_flag:
            return
        if self.control_thread.ident is not None and not self.control_thread.is_alive():
            self.control_thread = Thread(target=self.run)
        self.run_flag = True
        self.control_thread.start()

    def is_running(self):
        return self.run_flag

    def get(self):
        try:
            return self.queue_out.get_nowait()
        except Empty:
            return {}

    def run(self):
        while self.run_flag:
            try:
                self._collect_once()
            except Exception as exc:
                self._record_failure("event collection", exc)
            time.sleep(0.01)

    def stop(self):
        self.run_flag = False
        if self.control_thread.is_alive():
            self.control_thread.join(timeout=0.3)
            if self.control_thread.is_alive():
                self._record_failure(
                    "event controller shutdown",
                    RuntimeError("controller thread did not stop within 0.3 seconds"),
                )
                return
        self.logger.info("Everything in controller stopped")

    def flush_once(self):
        """Collect events once and expose failures through degraded diagnostics."""
        try:
            return self._collect_once()
        except Exception as exc:
            self._record_failure("event collection", exc)
            return False

    def _collect_once(self):
        self.any_events = False
        time.sleep(0.01)
        for detector in self.detectors:
            try:
                detector_name = detector.get_name()
                events = detector.get()
            except Exception as exc:
                if not self._record_detector_runtime_status(detector):
                    self._record_failure(
                        f"event detector {getattr(detector, 'module_id', type(detector).__name__)}",
                        exc,
                    )
                continue
            self._record_detector_runtime_status(detector)
            if events:
                self.events_detectors[detector_name] = events
                self.any_events = True
            else:
                self.events_detectors[detector_name] = []
        if self.any_events:
            self._publish_events_snapshot()
        return self.any_events

    def _record_detector_runtime_status(self, detector) -> bool:
        get_stats = getattr(detector, "get_runtime_stats", None)
        if not callable(get_stats):
            return False
        try:
            stats = get_stats()
        except Exception as exc:
            self._record_failure("event detector runtime status", exc)
            return True
        if not isinstance(stats, dict):
            return False

        module_id = str(
            stats.get("module_id")
            or getattr(detector, "module_id", type(detector).__name__)
        )
        detector_degraded = bool(stats.get("degraded"))
        reason = str(stats.get("last_error") or "module reports degraded status")
        with self._runtime_lock:
            if detector_degraded:
                previous = self._detector_failures.get(module_id)
                self._detector_failures[module_id] = reason
            else:
                previous = None
                self._detector_failures.pop(module_id, None)
            self._refresh_runtime_status()

        if detector_degraded and previous != reason:
            self.logger.error(
                "Event detector '%s' reports degraded runtime: %s",
                module_id,
                reason,
            )
        return detector_degraded

    def _refresh_runtime_status(self) -> None:
        with self._runtime_lock:
            self.degraded = self._controller_degraded or bool(self._detector_failures)
            if self._controller_degraded:
                self.last_error = self._controller_last_error
            elif self._detector_failures:
                module_id, reason = next(iter(self._detector_failures.items()))
                self.last_error = f"event detector {module_id}: {reason}"
            else:
                self.last_error = None

    def _record_failure(self, operation: str, exc: Exception) -> None:
        with self._runtime_lock:
            self._controller_degraded = True
            self._controller_last_error = f"{operation}: {type(exc).__name__}: {exc}"
            self._refresh_runtime_status()
        self.logger.error(
            "%s failed: %s",
            operation,
            exc,
            exc_info=(type(exc), exc, exc.__traceback__),
        )

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        self.stop()
        self.logger.info('Everything in controller released')

    def _publish_events_snapshot(self) -> None:
        snapshot = copy.deepcopy(self.events_detectors)
        try:
            self.queue_out.put_nowait(snapshot)
            with self._runtime_lock:
                self._events_published += 1
        except Full:
            with self._runtime_lock:
                self._queue_drops += 1
                drops = self._queue_drops
                self._controller_degraded = True
                self._controller_last_error = "event snapshot queue is full; snapshot was rejected"
                self._refresh_runtime_status()
            self.logger.error(
                "Event snapshot queue is full; snapshot was rejected (drops=%d)",
                drops,
            )
        except Exception as exc:
            self._record_failure("event snapshot publication", exc)

    def get_runtime_stats(self) -> dict:
        self._refresh_runtime_status()
        try:
            queue_size = self.queue_out.qsize()
        except Exception:
            queue_size = None
        with self._runtime_lock:
            return {
                "queue_size": queue_size,
                "queue_maxsize": self.queue_out_maxsize,
                "queue_drops": self._queue_drops,
                "events_published": self._events_published,
                "degraded": self.degraded,
                "last_error": self.last_error,
                "detector_failures": dict(self._detector_failures),
            }
