from abc import ABC, abstractmethod
import multiprocessing as mp
import logging
import logging.handlers
from queue import Full
from timeit import default_timer as timer

from .logger import get_module_logger


def _setup_child_process_logging(log_queue):
    """Configure logging in a child process to forward records via queue"""
    root = logging.getLogger()
    root.handlers.clear()
    if log_queue is not None:
        handler = logging.handlers.QueueHandler(log_queue)
        root.addHandler(handler)
        root.setLevel(logging.DEBUG)


class MpWorker(ABC):
    """Base class for multiprocessing workers

    Each worker runs in a separate OS process, receives data from
    input_queue, processes it in worker_impl(), and puts results
    into output_queue.  Sending None through input_queue is the
    poison-pill signal that terminates the worker loop gracefully
    """

    def __init__(self, input_queue, output_queue, log_queue=None):
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.log_queue = log_queue
        self.queue_timeout = 2
        self.output_timeout = 1.0
        # Родительский логгер нужен до инициализации child-process logging.
        self.logger = get_module_logger("mp_worker")
        # Shared flag so the parent can request a stop without poison pill
        self._stop_event = mp.Event()
        self.stats = {
            "processed_total": 0,
            "drops_total": 0,
            "put_wait_ms_total": 0.0,
        }

    def _init_logger(self):
        """Initialize logger inside child process"""
        _setup_child_process_logging(self.log_queue)
        self.logger = logging.getLogger(f"evileye.mp_worker.{mp.current_process().name}")

    @abstractmethod
    def init_worker(self):
        pass

    @abstractmethod
    def worker_impl(self, data):
        pass

    def cleanup(self):
        """Called before the worker loop exits -- override for resource cleanup"""
        pass

    def __call__(self):
        self._init_logger()
        try:
            self.init_worker()
        except Exception as e:
            if self.logger:
                self.logger.error(f"Worker init failed: {e}", exc_info=True)
            return

        if self.logger:
            self.logger.info(f"Process {mp.current_process().name} ready")

        while not self._stop_event.is_set():
            try:
                data = self.input_queue.get(timeout=self.queue_timeout)
                if data is None:
                    break
                results = self.worker_impl(data)
                put_started = timer()
                try:
                    self.output_queue.put(results, timeout=self.output_timeout)
                    self.stats["put_wait_ms_total"] += (timer() - put_started) * 1000.0
                except Full:
                    try:
                        _ = self.output_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        self.output_queue.put(results, timeout=self.output_timeout)
                        self.stats["put_wait_ms_total"] += (timer() - put_started) * 1000.0
                        self.stats["drops_total"] += 1
                    except Exception:
                        self.stats["drops_total"] += 1
                        if self.logger:
                            self.logger.warning(
                                "Worker output queue is full, dropping result"
                            )
                self.stats["processed_total"] += 1
            except mp.queues.Empty:
                continue
            except Exception as e:
                if self.logger:
                    self.logger.error(
                        f"Error in process {mp.current_process().name}: {e}",
                        exc_info=True,
                    )
                break

        try:
            self.cleanup()
        except Exception:
            pass

        if self.logger:
            if self.stats["processed_total"] > 0:
                avg_put_wait_ms = self.stats["put_wait_ms_total"] / float(
                    self.stats["processed_total"]
                )
                self.logger.info(
                    "Worker stats: processed_total=%d drops_total=%d avg_put_wait_ms=%.3f",
                    self.stats["processed_total"],
                    self.stats["drops_total"],
                    avg_put_wait_ms,
                )
            self.logger.info(f"Process {mp.current_process().name} exiting")
