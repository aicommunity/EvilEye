import multiprocessing as mp
import logging
import logging.handlers
import threading
import time
from typing import Iterable
from timeit import default_timer as timer
from .logger import get_module_logger
from .mp_context import get_spawn_context
from .mp_worker import run_mp_worker_entry
from .mp_session_registry import (
    cleanup_current_session_workers,
    register_worker_pid,
    unregister_worker_pid,
)


class MpControl:
    """Controller for a pool of MpWorker processes

    Manages input/output queues, process lifecycle, health monitoring,
    and graceful shutdown.  Workers are added via add_worker() and
    started together with start()
    """

    def __init__(
            self,
            max_input_size=None,
            max_output_size=None,
            name="MpControl",
            restart_on_exit=True,
            no_restart_exit_codes=None,
    ):
        self.name = name
        self.logger = get_module_logger(f"mp_control.{name}")
        self.workers_list = []
        self.restart_on_exit = bool(restart_on_exit)
        self.no_restart_exit_codes = set(no_restart_exit_codes or {-15})
        self._mp_ctx = get_spawn_context()

        if max_input_size is None:
            max_input_size = 8
        if max_input_size:
            self.input_queue = self._mp_ctx.Queue(maxsize=max_input_size)
        else:
            self.input_queue = self._mp_ctx.Queue()

        if max_output_size is None:
            max_output_size = 8
        if max_output_size:
            self.output_queue = self._mp_ctx.Queue(maxsize=max_output_size)
        else:
            self.output_queue = self._mp_ctx.Queue()
        self.processes: list[mp.Process] = []

        # Cross-process logging
        self._log_queue = self._mp_ctx.Queue()
        self._log_listener = None

        # Health monitoring
        self._monitor_thread = None
        self._monitor_stop = threading.Event()
        self._stopping = threading.Event()
        self._suppressed_restart_pids: set[int] = set()
        self._stats_lock = threading.Lock()
        self._stats = {
            "put_calls_total": 0,
            "put_wait_ms_total": 0.0,
            "get_calls_total": 0,
            "worker_restart_total": 0,
            "restart_suppressed_total": 0,
        }

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
        stop_event = self._mp_ctx.Event()
        worker = worker_class(
            self.input_queue,
            self.output_queue,
            log_queue=self._log_queue,
            stop_event=stop_event,
            *args,
            **kwargs,
        )
        self.workers_list.append(worker)
        return worker

    # -- Queue helpers ---------------------------------------------------

    def put(self, data, block=True, timeout=None):
        started = timer()
        self.input_queue.put(data, block=block, timeout=timeout)
        with self._stats_lock:
            self._stats["put_calls_total"] += 1
            self._stats["put_wait_ms_total"] += (timer() - started) * 1000.0

    def put_nowait(self, data):
        self.input_queue.put_nowait(data)

    def get(self, block=True, timeout=None):
        result = self.output_queue.get(block=block, timeout=timeout)
        with self._stats_lock:
            self._stats["get_calls_total"] += 1
        return result

    def get_nowait(self):
        return self.output_queue.get_nowait()

    def output_empty(self):
        return self.output_queue.empty()

    # -- Lifecycle -------------------------------------------------------

    def start(self):
        """Spawn all registered workers as daemon processes"""
        self._stopping.clear()
        self._suppressed_restart_pids.clear()
        self._start_log_listener()
        for worker in self.workers_list:
            p = self._mp_ctx.Process(
                target=run_mp_worker_entry,
                args=(
                    type(worker),
                    self.input_queue,
                    self.output_queue,
                    self._log_queue,
                    worker._stop_event,
                    worker.get_spawn_state(),
                ),
                daemon=True,
                name=f"{self.name}-worker",
            )
            p.start()
            self.processes.append(p)
            try:
                register_worker_pid(int(p.pid), self.name)
            except Exception:
                pass
            self.logger.info(f"Started worker process pid={p.pid}")

        self._start_health_monitor()

    def stop(self, timeout=5.0):
        """Gracefully stop all worker processes

        Sends a poison pill (None) for each worker, then waits up to
        *timeout* seconds for each process to finish.  Processes that
        do not exit in time are terminated forcefully
        """
        self._stopping.set()
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
            try:
                unregister_worker_pid(int(p.pid))
            except Exception:
                pass

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
                if not p.is_alive() and not self._monitor_stop.is_set() and not self._stopping.is_set():
                    if p.pid in self._suppressed_restart_pids:
                        continue
                    if not self.restart_on_exit:
                        with self._stats_lock:
                            self._stats["restart_suppressed_total"] += 1
                        self._suppressed_restart_pids.add(p.pid)
                        continue
                    if p.exitcode in self.no_restart_exit_codes:
                        self.logger.info(
                            "Worker pid=%s exited with code %s; restart suppressed by policy",
                            p.pid,
                            p.exitcode,
                        )
                        with self._stats_lock:
                            self._stats["restart_suppressed_total"] += 1
                        self._suppressed_restart_pids.add(p.pid)
                        continue
                    self.logger.warning(
                        f"Worker pid={p.pid} exited with code {p.exitcode}, "
                        f"restarting"
                    )
                    try:
                        w = self.workers_list[i]
                        new_p = self._mp_ctx.Process(
                            target=run_mp_worker_entry,
                            args=(
                                type(w),
                                self.input_queue,
                                self.output_queue,
                                self._log_queue,
                                w._stop_event,
                                w.get_spawn_state(),
                            ),
                            daemon=True,
                            name=f"{self.name}-worker",
                        )
                        new_p.start()
                        self.processes[i] = new_p
                        try:
                            register_worker_pid(int(new_p.pid), self.name)
                        except Exception:
                            pass
                        with self._stats_lock:
                            self._stats["worker_restart_total"] += 1
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

    def get_metrics(self) -> dict:
        with self._stats_lock:
            snapshot = dict(self._stats)
        put_calls = snapshot.get("put_calls_total", 0) or 0
        if put_calls > 0:
            snapshot["avg_put_wait_ms"] = snapshot["put_wait_ms_total"] / float(put_calls)
        else:
            snapshot["avg_put_wait_ms"] = 0.0
        snapshot["input_queue_size"] = self.input_queue.qsize()
        snapshot["output_queue_size"] = self.output_queue.qsize()
        snapshot["alive_workers"] = self.worker_count()
        return snapshot


def parse_mp_restart_policy(
        params: dict | None,
        *,
        default_restart_on_exit: bool,
        default_no_restart_exit_codes: Iterable[int] | None = None,
) -> tuple[bool, set[int]]:
    """Parse restart policy from module params."""
    params = params or {}
    restart_on_exit = bool(
        params.get("mp_restart_on_exit", default_restart_on_exit)
    )
    raw_codes = params.get("mp_no_restart_exit_codes", None)
    if raw_codes is None:
        codes = set(default_no_restart_exit_codes or {-15})
    elif isinstance(raw_codes, (list, tuple, set)):
        codes = set()
        for value in raw_codes:
            try:
                codes.add(int(value))
            except Exception:
                continue
    else:
        try:
            codes = {int(raw_codes)}
        except Exception:
            codes = set(default_no_restart_exit_codes or {-15})
    return restart_on_exit, codes
