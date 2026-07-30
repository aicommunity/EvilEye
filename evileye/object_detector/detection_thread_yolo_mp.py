from queue import Empty, Queue
import logging
import threading
import time
from typing import Callable, Optional

from .detection_thread_base import DetectionThreadBase
from ..core.frame import Frame
from ..core.frame_transport import FrameHandle, SharedFrameTransport
from ..core.gpu_errors import cuda_memory_snapshot, format_cuda_oom_message
from ..core.mp_async_bridge import MpAsyncBridge
from ..core.mp_pending_jobs import DetectorPendingJob
from ..core.mp_queue_config import (
    mp_control_queue_size,
    mp_drain_poll_sec,
    mp_pending_cap_detector,
)

utils = None


def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadYoloMp(DetectionThreadBase):
    """Detection thread backed by a child process via `MpControl`.

    Process mode uses feed + drain threads (like thread-mode async): the
    processing loop submits ROI batches to the worker without blocking on
    each ``get()``; results are finalized and pushed to ``queue_out`` when ready.
    """
    id_cnt = 0

    def __init__(self, model_name: str, stride: int, classes: list,
                 source_ids: list, roi: list, inf_params: dict,
                 restart_on_exit: bool, no_restart_exit_codes: set[int],
                 queue_out: Queue, logger_name: Optional[str] = None,
                 parent_logger: Optional[logging.Logger] = None,
                 on_cuda_oom_fatal: Optional[Callable[[str], None]] = None):
        from evileye.core.mp_control import MpControl
        from .mp_worker_yolo import MpWorkerYolo

        qsize = mp_control_queue_size(max(len(roi), 1), role="detector")
        self._on_cuda_oom_fatal = on_cuda_oom_fatal
        self._gpu_disabled = False
        self.mp_control = MpControl(
            max_input_size=qsize,
            max_output_size=qsize,
            name=f"det-mp-{DetectionThreadYoloMp.id_cnt}",
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
            on_worker_fatal_exit=self._handle_worker_fatal_exit,
        )
        self.mp_worker = self.mp_control.add_worker(MpWorkerYolo)
        self.model_name = model_name
        self.model = None
        self._frame_transport = SharedFrameTransport()
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)
        if parent_logger is not None:
            self.logger = parent_logger
        self.mp_worker.set_params(self.model_name, self.classes, self.inf_params)
        self.mp_control.start()
        DetectionThreadYoloMp.id_cnt += 1

        self.processing_thread = None
        self._mp_feed_thread = threading.Thread(
            target=self._mp_det_feed_loop, daemon=True,
        )
        self._mp_drain_thread = threading.Thread(
            target=self._mp_det_drain_loop, daemon=True,
        )
        self._mp_pending_cap = mp_pending_cap_detector(max(len(roi), 1))
        self._bridge: MpAsyncBridge[DetectorPendingJob] | None = None
        self._stopped = False
        self._init_bridge()

    def _init_bridge(self) -> None:
        self._bridge = MpAsyncBridge(
            pending_cap=self._mp_pending_cap,
            mp_control=self.mp_control,
            release_on_drop=self._release_detector_job,
            logger=self.logger,
        )

    def start(self) -> None:
        """Start feed/drain threads (not the base processing_thread)."""
        self.run_flag = True
        self._mp_feed_thread.start()
        self._mp_drain_thread.start()

    def stop(self) -> None:
        """Stop MP worker and feed/drain threads."""
        if self._stopped:
            return
        self._stopped = True
        self.run_flag = False
        for name, thread in (("feed", self._mp_feed_thread), ("drain", self._mp_drain_thread)):
            if thread is not None and thread.is_alive():
                thread.join(timeout=1.5)
                if thread.is_alive():
                    self.logger.warning("Detection MP %s thread did not stop within 1.5s", name)
        if self.mp_control is not None:
            self.mp_control.stop()
            self.mp_control = None
        if self._bridge is not None:
            self._bridge.clear()
            self._bridge = None
        self.logger.info("Detection thread stopped")

    def init_detection_implementation(self) -> None:
        """Multiprocessing worker handles model initialization."""
        return None

    def _release_handles(self, handles: list[FrameHandle]) -> None:
        for handle in handles or []:
            try:
                self._frame_transport.release_frame(handle)
            except Exception:
                pass

    def _release_detector_job(self, job: DetectorPendingJob) -> None:
        self._release_handles(job.handles)

    def mp_pending_depth(self) -> int:
        if self._bridge is None:
            return 0
        return self._bridge.depth()

    def mp_diag_put_dropped(self) -> int:
        if self._bridge is None:
            return 0
        return self._bridge.diag_put_dropped()

    def mp_diag_pending_evict(self) -> int:
        if self._bridge is None:
            return 0
        return self._bridge.diag_pending_evict()

    def is_gpu_disabled(self) -> bool:
        return self._gpu_disabled

    def _handle_worker_fatal_exit(self, slot_index: int, exit_code: int, pool_name: str) -> None:
        if self._gpu_disabled:
            return
        self._gpu_disabled = True
        message = format_cuda_oom_message(
            component=pool_name,
            detail="detection worker disabled after fatal CUDA OOM",
            extra={
                "slot": slot_index,
                "exit_code": exit_code,
                "source_ids": self.source_ids,
                "cuda": cuda_memory_snapshot(),
            },
        )
        self.logger.error(message)
        self._drain_mp_output_queue()
        self._flush_pending_jobs_empty()
        try:
            from evileye.core.mp_cuda_startup import get_mp_cuda_startup_health

            if get_mp_cuda_startup_health().record_fatal_oom():
                restart_cb = get_mp_cuda_startup_health().restart_callback
                if restart_cb is not None:
                    restart_cb()
        except Exception as exc:
            self.logger.error("Mass CUDA OOM startup check failed: %s", exc, exc_info=True)
        callback = self._on_cuda_oom_fatal
        if callback is not None:
            try:
                callback(message)
            except Exception as exc:
                self.logger.error("CUDA OOM callback failed: %s", exc, exc_info=True)

    def _drain_mp_output_queue(self) -> None:
        if self.mp_control is None:
            return
        while True:
            try:
                self.mp_control.get_nowait()
            except Exception:
                break

    def _flush_pending_jobs_empty(self) -> None:
        if self._bridge is None:
            return
        while True:
            job = self._bridge.pop_head()
            if job is None:
                break
            try:
                detection_result_list = self._detection_result_from_predict(
                    job.split_image,
                    [None] * len(job.split_image),
                )
                self._put_detection_output(detection_result_list, job.capture_image)
            except Exception as exc:
                self.logger.error("Failed to flush pending MP job after CUDA OOM: %s", exc)
            finally:
                self._release_handles(job.handles)

    def _put_empty_detection_for_capture(self, capture_image) -> None:
        from .detection_preprocess import split_capture_for_detection

        split_image = split_capture_for_detection(
            capture_image, self.roi, self.roi_coords_per_camera
        )
        if not split_image:
            return
        detection_result_list = self._detection_result_from_predict(
            split_image,
            [None] * len(split_image),
        )
        self._put_detection_output(detection_result_list, capture_image)

    def _build_mp_payload(
        self, split_image: list, capture_image=None
    ) -> tuple[list, list[FrameHandle]]:
        handles: list[FrameHandle] = []
        payload: list = []
        now_ts = time.time()
        for idx, roi_entry in enumerate(split_image):
            frame = roi_entry[0]
            image = frame.image
            handle = self._frame_transport.alloc_frame(
                image=image,
                frame_id=idx,
                timestamp=now_ts,
            )
            handles.append(handle)
            payload.append(handle)
            # Release ROI crop bitmaps while pending in SHM. Never clear the original
            # capture frame: empty-ROI path reuses it for tracker/GUI (Cam2/Cam5).
            if capture_image is not None and frame is capture_image:
                continue
            frame.image = None
        return payload, handles

    def _enqueue_mp_det_job(
        self, split_image: list, capture_image, payload: list, handles: list[FrameHandle]
    ) -> bool:
        if self._bridge is None:
            return False
        job = DetectorPendingJob(split_image, capture_image, handles)
        return self._bridge.enqueue(payload, job)

    def _put_detection_output(self, detection_result_list, capture_image) -> None:
        if detection_result_list is None:
            return
        try:
            self.queue_out.put_nowait([detection_result_list, capture_image])
        except Exception:
            try:
                _ = self.queue_out.get_nowait()
                self.queue_out.put_nowait([detection_result_list, capture_image])
            except Exception:
                self.logger.warning(
                    "Output queue full, dropping detection result for %s:%s",
                    capture_image.source_id,
                    capture_image.frame_id,
                )

    def _mp_det_feed_loop(self) -> None:
        """queue_in -> mp_control input (non-blocking per frame batch)."""
        self.init_detection_implementation()
        while self.run_flag:
            try:
                image = self.queue_in.get(timeout=0.5)
            except Empty:
                continue
            except Exception:
                continue
            if not self.run_flag or image is None:
                continue
            from .detection_preprocess import split_capture_for_detection

            split_image = split_capture_for_detection(
                image, self.roi, self.roi_coords_per_camera
            )
            if not split_image:
                continue
            if self._gpu_disabled or (self.mp_control is not None and not self.mp_control.is_operational()):
                self._put_empty_detection_for_capture(image)
                continue
            try:
                payload, handles = self._build_mp_payload(split_image, capture_image=image)
                self._enqueue_mp_det_job(split_image, image, payload, handles)
            except Exception as e:
                if self.run_flag:
                    self.logger.error("Error in MP detection feed loop: %s", e)

    def _mp_det_drain_loop(self) -> None:
        """mp_control output -> queue_out when YOLO worker finishes."""
        while self.run_flag:
            if self.mp_control is None or self._bridge is None:
                break
            try:
                predict_results = self.mp_control.get(timeout=mp_drain_poll_sec())
            except Empty:
                if self._gpu_disabled:
                    job = self._bridge.pop_head()
                    if job is not None:
                        try:
                            detection_result_list = self._detection_result_from_predict(
                                job.split_image,
                                [None] * len(job.split_image),
                            )
                            self._put_detection_output(detection_result_list, job.capture_image)
                        finally:
                            self._release_handles(job.handles)
                continue
            except Exception:
                continue
            job = self._bridge.pop_head()
            if job is None:
                continue
            try:
                if predict_results is None:
                    predict_results = [None] * len(job.split_image)
                elif not isinstance(predict_results, list):
                    predict_results = [predict_results]
                detection_result_list = self._detection_result_from_predict(
                    job.split_image, predict_results
                )
                self._put_detection_output(detection_result_list, job.capture_image)
            except Exception as e:
                if self.run_flag:
                    self.logger.error("Error in MP detection drain loop: %s", e)
            finally:
                self._release_handles(job.handles)

    def predict(self, images: list) -> list:
        """Synchronous RPC fallback (tests); production path uses feed/drain."""
        payload, handles = [], []
        now_ts = time.time()
        for idx, image in enumerate(images):
            handle = self._frame_transport.alloc_frame(
                image=image,
                frame_id=idx,
                timestamp=now_ts,
            )
            handles.append(handle)
            payload.append(handle)
        try:
            self.mp_control.put(payload)
            return self.mp_control.get()
        finally:
            self._release_handles(handles)

    def get_bboxes(self, result, roi: list) -> tuple[list, list, list]:
        if result is None:
            return [], [], []
        from .bbox_utils import (
            clip_xyxy_list,
            mp_dict_list_to_image_coords,
            roi_boxes_to_image_coords,
        )

        frame_entry = roi[0]
        x_off, y_off = roi[1][0], roi[1][1]
        try:
            if isinstance(result, list):
                bboxes_coords, confidences, ids = mp_dict_list_to_image_coords(
                    result, (x_off, y_off), logger=self.logger
                )
            else:
                bboxes_coords, confidences, ids = roi_boxes_to_image_coords(
                    result, (x_off, y_off), logger=self.logger
                )
        except Exception:
            return [], [], []

        img = frame_entry.image if isinstance(frame_entry, Frame) else None
        if img is not None and len(img.shape) >= 2:
            h, w = img.shape[:2]
            bboxes_coords = clip_xyxy_list(bboxes_coords, w, h)
        return bboxes_coords, confidences, ids
