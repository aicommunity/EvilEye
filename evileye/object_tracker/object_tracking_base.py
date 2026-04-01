from abc import abstractmethod
from ..core.base_class import EvilEyeBase
from queue import Full, Queue
import multiprocessing as mp
import threading
from .tracking_results import TrackingResultList

EXEC_MODE_THREAD = "thread"
EXEC_MODE_PROCESS = "process"


class ObjectTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.execution_mode = EXEC_MODE_THREAD

        self.queue_in = None
        self.queue_out = None
        self.queue_dropped_id = None
        self._init_queues()

        self.source_ids = []
        self.processing_thread = None

        # Multiprocessing pool (used when execution_mode == "process")
        self._mp_control = None

    def _init_queues(self):
        if self.execution_mode == EXEC_MODE_PROCESS:
            self.queue_in = mp.Queue(maxsize=2)
            self.queue_out = mp.Queue(maxsize=4)
            self.queue_dropped_id = mp.Queue()
        else:
            self.queue_in = Queue(maxsize=2)
            self.queue_out = Queue(maxsize=4)
            self.queue_dropped_id = Queue()

    def put(self, det_info, force=False):
        dropped_id = []
        result = True
        if self.queue_in.full():
            if force:
                dropped_data = self.queue_in.get()
                dropped_id.append(dropped_data[1].source_id)
                dropped_id.append(dropped_data[1].frame_id)
                result = True
            else:
                dropped_id.append(det_info[1].source_id)
                dropped_id.append(det_info[1].frame_id)
                result = False
        if len(dropped_id) > 0:
            self.queue_dropped_id.put(dropped_id)

        if result:
            self.queue_in.put(det_info)

        return result

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def _put_out_drop_oldest(self, item) -> None:
        """Put to queue_out with drop-oldest behavior when full."""
        try:
            self.queue_out.put_nowait(item)
            return
        except Full:
            try:
                _ = self.queue_out.get_nowait()
            except Exception:
                pass
            try:
                self.queue_out.put_nowait(item)
            except Exception:
                pass

    def get_dropped_ids(self) -> list:
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_oueue_out_size(self):
        return self.queue_out.qsize()

    def get_source_ids(self):
        return self.source_ids

    def start(self):
        self.run_flag = True
        if self.execution_mode == EXEC_MODE_PROCESS and self._mp_control is not None:
            # Child process is already started during init
            # Start the dispatcher thread that feeds queue_in -> mp_control
            if self.processing_thread is not None:
                self.processing_thread.start()
        elif self.processing_thread is not None:
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        try:
            self.queue_in.put(None)
        except Exception:
            pass
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2.0)
            if self.processing_thread.is_alive():
                self.logger.warning("Tracker processing_thread did not stop within 2s")
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        self.logger.info('Tracker stopped')

    def init_impl(self, **kwargs):
        new_mode = self.params.get('execution_mode', EXEC_MODE_THREAD) if self.params else EXEC_MODE_THREAD
        if new_mode != self.execution_mode:
            self.execution_mode = new_mode
            self._init_queues()

        if self.execution_mode == EXEC_MODE_PROCESS:
            self._init_process_mode(**kwargs)
        else:
            self.processing_thread = threading.Thread(target=self._process_impl)

    def _init_process_mode(self, **kwargs):
        """Initialize tracking in a child process via MpControl"""
        from ..core.mp_control import MpControl
        from .mp_worker_tracker import MpWorkerTracker

        self._mp_control = MpControl(
            max_input_size=4,
            name=f"tracker-{id(self)}",
        )
        worker = self._mp_control.add_worker(MpWorkerTracker)
        worker.set_params(self.params if self.params else {})
        self._mp_control.start()

        # Dispatcher thread: reads from queue_in, sends to mp_control,
        # reads results and puts them into queue_out
        self.processing_thread = threading.Thread(
            target=self._process_dispatch_loop, daemon=True,
        )

    def _process_dispatch_loop(self):
        """Dispatcher loop for process mode"""
        from time import sleep
        while self.run_flag:
            sleep(0.01)
            try:
                detections = self.queue_in.get(timeout=0.5)
            except Exception:
                continue
            if detections is None:
                continue
            try:
                self._mp_control.put(detections)
                result = self._mp_control.get(timeout=10.0)
                self._put_out_drop_oldest(result)
            except Exception as e:
                self.logger.error(f"Error in tracking dispatch loop: {e}")

    def release_impl(self):
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        if self.processing_thread is not None:
            del self.processing_thread
            self.processing_thread = None

    @abstractmethod
    def _process_impl(self):
        pass
