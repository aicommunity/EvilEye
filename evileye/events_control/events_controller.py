from threading import Thread
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

    def set_params_impl(self):
        pass

    def get_params_impl(self):
        return dict()

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
                self._record_failure(
                    f"event detector {getattr(detector, 'module_id', type(detector).__name__)}",
                    exc,
                )
                continue
            if events:
                self.events_detectors[detector_name] = events
                self.any_events = True
            else:
                self.events_detectors[detector_name] = []
        if self.any_events:
            self._publish_events_snapshot()
        return self.any_events

    def _record_failure(self, operation: str, exc: Exception) -> None:
        self.degraded = True
        self.last_error = f"{operation}: {type(exc).__name__}: {exc}"
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
            self._events_published += 1
        except Full:
            self._queue_drops += 1
            self.degraded = True
            self.last_error = "event snapshot queue is full; snapshot was rejected"
            self.logger.error(
                "Event snapshot queue is full; snapshot was rejected (drops=%d)",
                self._queue_drops,
            )
        except Exception as exc:
            self._record_failure("event snapshot publication", exc)

    def get_runtime_stats(self) -> dict:
        try:
            queue_size = self.queue_out.qsize()
        except Exception:
            queue_size = None
        return {
            "queue_size": queue_size,
            "queue_maxsize": self.queue_out_maxsize,
            "queue_drops": self._queue_drops,
            "events_published": self._events_published,
            "degraded": self.degraded,
            "last_error": self.last_error,
        }
