from abc import abstractmethod
from ..core.base_class import EvilEyeBase
from queue import Full, Queue, Empty
import threading
import time
from .tracking_results import TrackingResultList
from ..core.frame_transport import SharedFrameTransport

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
        self._stopping = threading.Event()
        self._frame_transport = SharedFrameTransport()

    def _init_queues(self):
        # Tracker dispatcher and pipeline live in the same process.
        # Keep local queues thread-based even in process execution mode;
        # true IPC boundary is _mp_control worker queues.
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
        self._stopping.clear()
        if self.execution_mode == EXEC_MODE_PROCESS and self._mp_control is not None:
            # Child process is already started during init
            # Start the dispatcher thread that feeds queue_in -> mp_control
            if self.processing_thread is not None:
                self.processing_thread.start()
        elif self.processing_thread is not None:
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self._stopping.set()
        try:
            self.queue_in.put_nowait(None)
        except Exception:
            try:
                _ = self.queue_in.get_nowait()
            except Exception:
                pass
            try:
                self.queue_in.put_nowait(None)
            except Exception:
                pass
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=1.5)
            if self.processing_thread.is_alive():
                self.logger.warning("Tracker processing_thread did not stop within 1.5s")
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
        from ..core.mp_control import MpControl, parse_mp_restart_policy
        from .mp_worker_tracker import MpWorkerTracker
        restart_on_exit, no_restart_exit_codes = parse_mp_restart_policy(
            self.params,
            default_restart_on_exit=True,
        )

        self._mp_control = MpControl(
            max_input_size=4,
            name=f"tracker-{id(self)}",
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
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
        while self.run_flag:
            if self._mp_control is None:
                break
            try:
                detections = self.queue_in.get(timeout=0.5)
            except Empty:
                continue
            if detections is None:
                continue
            try:
                packed, frame_handle = self._pack_for_worker(detections)
                try:
                    self._mp_control.put_nowait(packed)
                except Exception:
                    # Drop oldest pending input and retry non-blocking put.
                    try:
                        _ = self._mp_control.input_queue.get_nowait()
                    except Exception:
                        pass
                    try:
                        self._mp_control.put_nowait(packed)
                    except Exception:
                        if frame_handle is not None:
                            try:
                                self._frame_transport.release_frame(frame_handle)
                            except Exception:
                                pass
                        continue
                result = None
                while self.run_flag and not self._stopping.is_set():
                    try:
                        result = self._mp_control.get(timeout=0.25)
                        break
                    except Empty:
                        continue
                    except Exception:
                        break
                if result is None:
                    if frame_handle is not None:
                        try:
                            self._frame_transport.release_frame(frame_handle)
                        except Exception:
                            pass
                    continue
                if isinstance(result, (list, tuple)) and len(result) == 2:
                    self._put_out_drop_oldest(result)
                else:
                    # New fast-path: worker returns only tracking payload,
                    # keep original frame in parent process.
                    if (
                            isinstance(detections, (list, tuple))
                            and len(detections) >= 2
                    ):
                        self._put_out_drop_oldest((result, detections[1]))
                    else:
                        self._put_out_drop_oldest(result)
                if frame_handle is not None:
                    try:
                        self._frame_transport.release_frame(frame_handle)
                    except Exception:
                        pass
            except Full:
                # Backpressure: keep tracker loop responsive during shutdown/load spikes.
                continue
            except Empty:
                continue
            except Exception as e:
                if self.run_flag:
                    self.logger.error(f"Error in tracking dispatch loop: {e}")

    def _pack_for_worker(self, detections):
        """Pack tracking input for child process using frame descriptor."""
        if not (isinstance(detections, (list, tuple)) and len(detections) >= 2):
            return detections, None
        det_result, frame = detections[0], detections[1]
        image = getattr(frame, "image", None)
        if image is None:
            return detections, None
        frame_handle = self._frame_transport.alloc_frame(
            image=image,
            frame_id=int(getattr(frame, "frame_id", 0) or 0),
            timestamp=float(getattr(frame, "time_stamp", time.time()) or time.time()),
        )
        frame_meta = {
            "source_id": getattr(frame, "source_id", None),
            "frame_id": getattr(frame, "frame_id", None),
            "time_stamp": getattr(frame, "time_stamp", None),
            "current_video_frame": getattr(frame, "current_video_frame", None),
            "current_video_position": getattr(frame, "current_video_position", None),
            "source_video_duration": getattr(frame, "source_video_duration", None),
        }
        packed = {
            "detection_result": det_result,
            "frame_handle": frame_handle,
            "frame_meta": frame_meta,
        }
        return packed, frame_handle

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
