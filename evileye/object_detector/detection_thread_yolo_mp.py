from queue import Queue
import logging
import time
from typing import Optional

from .detection_thread_base import DetectionThreadBase
from ..core.frame_transport import FrameHandle, SharedFrameTransport

utils = None


def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadYoloMp(DetectionThreadBase):
    """Detection thread backed by a child process via `MpControl`.

    The heavy YOLO inference runs in a separate OS process, bypassing
    the GIL.  The thread wrapper keeps the same put/get interface so
    the rest of the pipeline is unaware of the change
    """
    id_cnt = 0

    def __init__(self, model_name: str, stride: int, classes: list,
                 source_ids: list, roi: list, inf_params: dict,
                 restart_on_exit: bool, no_restart_exit_codes: set[int],
                 queue_out: Queue, logger_name: Optional[str] = None,
                 parent_logger: Optional[logging.Logger] = None):
        from evileye.core.mp_control import MpControl
        from .mp_worker_yolo import MpWorkerYolo

        self.mp_control = MpControl(
            max_input_size=max(len(roi), 2),
            name=f"det-mp-{DetectionThreadYoloMp.id_cnt}",
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
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

    def init_detection_implementation(self) -> None:
        """Multiprocessing worker handles model initialization."""
        return None

    def predict(self, images: list) -> list:
        frame_handles: list[FrameHandle] = []
        payload = []
        now_ts = time.time()
        for idx, image in enumerate(images):
            handle = self._frame_transport.alloc_frame(
                image=image,
                frame_id=idx,
                timestamp=now_ts,
            )
            frame_handles.append(handle)
            payload.append(handle)
        try:
            self.mp_control.put(payload)
            return self.mp_control.get()
        finally:
            for handle in frame_handles:
                try:
                    self._frame_transport.release_frame(handle)
                except Exception:
                    pass

    def get_bboxes(self, result, roi: list) -> tuple[list, list, list]:
        bboxes_coords = []
        confidences = []
        ids = []
        if result is None:
            return bboxes_coords, confidences, ids
        try:
            if isinstance(result, list):
                coords = [x.get("bbox_xyxy", []) for x in result if isinstance(x, dict)]
                confs = [x.get("confidence", 0.0) for x in result if isinstance(x, dict)]
                class_ids = [x.get("class_id", -1) for x in result if isinstance(x, dict)]
            else:
                boxes = result.boxes.numpy()
                coords = boxes.xyxy
                confs = boxes.conf
                class_ids = boxes.cls
            for coord, class_id, conf in zip(coords, class_ids, confs):
                utils_module = get_utils()
                abs_coords = utils_module.roi_to_image(coord, roi[1][0], roi[1][1])
                bboxes_coords.append(abs_coords)
                confidences.append(conf)
                ids.append(class_id)
        except Exception:
            pass
        return bboxes_coords, confidences, ids

    def stop(self):
        """Stop the child process and the thread wrapper"""
        super().stop()
        if self.mp_control is not None:
            self.mp_control.stop()
