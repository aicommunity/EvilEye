import multiprocessing as mp
import logging
import logging.handlers
import threading
import time
from .logger import get_module_logger


class MpControl:
    """Controller for a pool of MpWorker processes

    Manages input/output queues, process lifecycle, health monitoring,
    and graceful shutdown.  Workers are added via add_worker() and
    started together with start()
    """

    def __init__(self, max_input_size=None, max_output_size=None, name="MpControl"):
        self.name = name
        self.logger = get_module_logger(f"mp_control.{name}")
        self.workers_list = []

        if max_input_size:
            self.input_queue = mp.Queue(maxsize=max_input_size)
        else:
            self.input_queue = mp.Queue()

        if max_output_size:
            self.output_queue = mp.Queue(maxsize=max_output_size)
        else:
            self.output_queue = mp.Queue()
        self.processes: list[mp.Process] = []

        # Cross-process logging
        self._log_queue = mp.Queue()
        self._log_listener = None

        # Health monitoring
        self._monitor_thread = None
        self._monitor_stop = threading.Event()

    # -- Logging bridge --------------------------------------------------

    def _start_log_listener(self):
        """Start a thread that reads log records from child processes"""
        self._log_listener = threading.Thread(
            target=self._log_listener_loop, daemon=True
        )
        self._log_listener.start()

    def _log_listener_loop(self):
        while not self._monitor_stop.is_set():
            try:
                record = self._log_queue.get(timeout=0.5)
                if record is None:
                    break
                logger = logging.getLogger(record.name)
                logger.handle(record)
            except Exception:
                continue

    def _stop_log_listener(self):
        try:
            self._log_queue.put_nowait(None)
        except Exception:
            pass

    # -- Worker management -----------------------------------------------

    def add_worker(self, worker_class, *args, **kwargs):
        """Instantiate a worker and register it

        The worker receives shared input/output queues and the log queue
        so that logging from child processes is forwarded to the parent
        """
        worker = worker_class(
            self.input_queue, self.output_queue, log_queue=self._log_queue,
            *args, **kwargs,
        )
        self.workers_list.append(worker)
        return worker

    # -- Queue helpers ---------------------------------------------------

    def put(self, data, block=True, timeout=None):
        self.input_queue.put(data, block=block, timeout=timeout)

    def put_nowait(self, data):
        self.input_queue.put_nowait(data)

    def get(self, block=True, timeout=None):
        return self.output_queue.get(block=block, timeout=timeout)

    def get_nowait(self):
        return self.output_queue.get_nowait()

    def output_empty(self):
        return self.output_queue.empty()

    # -- Lifecycle -------------------------------------------------------

    def start(self):
        """Spawn all registered workers as daemon processes"""
        self._start_log_listener()
        for worker in self.workers_list:
            p = mp.Process(target=worker, daemon=True, name=f"{self.name}-worker")
            p.start()
            self.processes.append(p)
            self.logger.info(f"Started worker process pid={p.pid}")

        self._start_health_monitor()

    def stop(self, timeout=5.0):
        """Gracefully stop all worker processes

        Sends a poison pill (None) for each worker, then waits up to
        *timeout* seconds for each process to finish.  Processes that
        do not exit in time are terminated forcefully
        """
        self._monitor_stop.set()

        # Send poison pills
        for _ in self.workers_list:
            try:
                self.input_queue.put_nowait(None)
            except Exception:
                pass

        # Also set the stop event on each worker
        for w in self.workers_list:
            if hasattr(w, "_stop_event"):
                w._stop_event.set()

        # Join with timeout
        deadline = time.monotonic() + timeout
        for p in self.processes:
            remaining = max(0.1, deadline - time.monotonic())
            p.join(timeout=remaining)
            if p.is_alive():
                self.logger.warning(f"Force-terminating worker pid={p.pid}")
                p.terminate()
                p.join(timeout=1.0)
                if p.is_alive():
                    self.logger.error(f"Force-killing worker pid={p.pid}")
                    p.kill()

        self.processes.clear()
        self._stop_log_listener()

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

        self.logger.info(f"MpControl '{self.name}' stopped")

    # -- Health monitoring -----------------------------------------------

    def _start_health_monitor(self):
        self._monitor_stop.clear()
        self._monitor_thread = threading.Thread(
            target=self._health_monitor_loop, daemon=True
        )
        self._monitor_thread.start()

    def _health_monitor_loop(self):
        while not self._monitor_stop.is_set():
            for i, p in enumerate(self.processes):
                if not p.is_alive() and not self._monitor_stop.is_set():
                    self.logger.warning(
                        f"Worker pid={p.pid} exited with code {p.exitcode}, "
                        f"restarting"
                    )
                    try:
                        new_p = mp.Process(
                            target=self.workers_list[i],
                            daemon=True,
                            name=f"{self.name}-worker",
                        )
                        new_p.start()
                        self.processes[i] = new_p
                        self.logger.info(
                            f"Restarted worker as pid={new_p.pid}"
                        )
                    except Exception as e:
                        self.logger.error(f"Failed to restart worker: {e}")
            self._monitor_stop.wait(timeout=2.0)

    # -- Diagnostics -----------------------------------------------------

    def is_alive(self) -> bool:
        return any(p.is_alive() for p in self.processes)

    def worker_count(self) -> int:
        return sum(1 for p in self.processes if p.is_alive())
