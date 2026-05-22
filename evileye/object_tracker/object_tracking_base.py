from abc import abstractmethod
import datetime
from collections import deque
from ..core.base_class import EvilEyeBase
from queue import Full, Queue, Empty
import threading
import time
from .tracking_results import TrackingResultList
from ..core.frame_transport import SharedFrameTransport
from ..core.frame import Frame
from ..object_detector.object_detection_base import DetectionResultList

from ..core.processor_base import (
    DEFAULT_EXECUTION_MODE,
    EXEC_MODE_PROCESS,
    EXEC_MODE_THREAD,
)

from ..core.mp_queue_config import (
    mp_control_queue_size,
    mp_drain_poll_sec,
    tracker_input_queue_size,
    tracker_output_queue_size,
)


def _empty_tracking_output_for_input(
    det_result: DetectionResultList,
    frame: Frame,
) -> tuple[TrackingResultList, Frame]:
    tracks_info = TrackingResultList()
    tracks_info.source_id = (
        det_result.source_id if det_result.source_id is not None else frame.source_id
    )
    tracks_info.frame_id = (
        det_result.frame_id if det_result.frame_id is not None else frame.frame_id
    )
    tracks_info.time_stamp = (
        frame.time_stamp if frame.time_stamp is not None else datetime.datetime.now()
    )
    return tracks_info, frame


class ObjectTrackingBase(EvilEyeBase):
    ResultType = TrackingResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.execution_mode = DEFAULT_EXECUTION_MODE

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
        self._diag_mp_get_timeout = 0
        self._diag_mp_put_dropped = 0
        self._mp_feed_thread: threading.Thread | None = None
        self._mp_drain_thread: threading.Thread | None = None
        self._mp_pending: deque = deque()
        self._mp_pending_lock = threading.Lock()

    def _init_queues(self):
        # Tracker dispatcher and pipeline live in the same process.
        # Keep local queues thread-based even in process execution mode;
        # true IPC boundary is _mp_control worker queues.
        self.queue_in = Queue(maxsize=tracker_input_queue_size())
        self.queue_out = Queue(maxsize=tracker_output_queue_size())
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
            if self._mp_feed_thread is not None:
                self._mp_feed_thread.start()
            if self._mp_drain_thread is not None:
                self._mp_drain_thread.start()
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
        for name, thread in (
            ("mp_feed", self._mp_feed_thread),
            ("mp_drain", self._mp_drain_thread),
            ("processing", self.processing_thread),
        ):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.5)
                if thread.is_alive():
                    self.logger.warning("Tracker %s thread did not stop within 1.5s", name)
        self._clear_mp_pending()
        self.logger.info('Tracker stopped')

    def init_impl(self, **kwargs):
        new_mode = (
            self.params.get('execution_mode', DEFAULT_EXECUTION_MODE)
            if self.params
            else DEFAULT_EXECUTION_MODE
        )
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

        tq = mp_control_queue_size(1, role="tracker")
        self._mp_control = MpControl(
            max_input_size=tq,
            max_output_size=tq,
            name=f"tracker-{id(self)}",
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
        )
        worker = self._mp_control.add_worker(MpWorkerTracker)
        worker.set_params(self.params if self.params else {})
        self._mp_control.start()

        # Thread mode: BoT-SORT runs in _process_impl. Process mode: feed + drain
        # (same async contract as thread — queue_in/queue_out, no per-frame RPC wait).
        self.processing_thread = None
        self._mp_feed_thread = threading.Thread(
            target=self._mp_tracker_feed_loop, daemon=True,
        )
        self._mp_drain_thread = threading.Thread(
            target=self._mp_tracker_drain_loop, daemon=True,
        )

    def _release_frame_handle(self, frame_handle) -> None:
        if frame_handle is None:
            return
        try:
            self._frame_transport.release_frame(frame_handle)
        except Exception:
            pass

    def _clear_mp_pending(self) -> None:
        with self._mp_pending_lock:
            while self._mp_pending:
                _, frame_handle = self._mp_pending.popleft()
                self._release_frame_handle(frame_handle)

    def _enqueue_mp_tracker_job(self, detections, packed, frame_handle) -> bool:
        """Queue job for FIFO worker and submit packed payload to MpControl."""
        with self._mp_pending_lock:
            self._mp_pending.append((detections, frame_handle))
        try:
            self._mp_control.put_nowait(packed)
            return True
        except Exception:
            pass
        try:
            _ = self._mp_control.input_queue.get_nowait()
        except Exception:
            pass
        with self._mp_pending_lock:
            if self._mp_pending:
                _, dropped_handle = self._mp_pending.popleft()
                self._release_frame_handle(dropped_handle)
        try:
            self._mp_control.put_nowait(packed)
            return True
        except Exception:
            with self._mp_pending_lock:
                if self._mp_pending:
                    tail_det, _ = self._mp_pending[-1]
                    if tail_det is detections:
                        self._mp_pending.pop()
            self._release_frame_handle(frame_handle)
            if isinstance(detections, (list, tuple)) and len(detections) >= 2:
                frame = detections[1]
                try:
                    self.queue_dropped_id.put_nowait(
                        [frame.source_id, frame.frame_id]
                    )
                except Exception:
                    pass
                self._diag_mp_put_dropped += 1
            return False

    def _emit_mp_tracker_result(self, detections, result) -> None:
        if result is None:
            if isinstance(detections, (list, tuple)) and len(detections) >= 2:
                det_result, frame = detections[0], detections[1]
                if isinstance(det_result, DetectionResultList) and isinstance(frame, Frame):
                    self._put_out_drop_oldest(
                        _empty_tracking_output_for_input(det_result, frame)
                    )
            return
        if isinstance(result, (list, tuple)) and len(result) == 2:
            self._put_out_drop_oldest(result)
            return
        if isinstance(detections, (list, tuple)) and len(detections) >= 2:
            self._put_out_drop_oldest((result, detections[1]))
            return
        self._put_out_drop_oldest(result)

    def _mp_tracker_feed_loop(self):
        """Process mode: queue_in -> mp_control input (non-blocking)."""
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
                self._enqueue_mp_tracker_job(detections, packed, frame_handle)
            except Exception as e:
                if self.run_flag:
                    self.logger.error("Error in MP tracker feed loop: %s", e)

    def _mp_tracker_drain_loop(self):
        """Process mode: mp_control output -> queue_out (poll, no per-job blocking)."""
        while self.run_flag:
            if self._mp_control is None:
                break
            try:
                result = self._mp_control.get(timeout=mp_drain_poll_sec())
            except Empty:
                continue
            except Exception:
                continue
            with self._mp_pending_lock:
                if not self._mp_pending:
                    continue
                detections, frame_handle = self._mp_pending.popleft()
            try:
                self._emit_mp_tracker_result(detections, result)
            except Exception as e:
                if self.run_flag:
                    self.logger.error("Error in MP tracker drain loop: %s", e)
            finally:
                self._release_frame_handle(frame_handle)

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
        self._clear_mp_pending()
        self.processing_thread = None
        self._mp_feed_thread = None
        self._mp_drain_thread = None

    @abstractmethod
    def _process_impl(self):
        pass
