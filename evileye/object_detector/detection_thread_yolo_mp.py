from queue import Queue
from .detection_thread_base import DetectionThreadBase

utils = None

def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadYoloMp(DetectionThreadBase):
    """Detection thread backed by a child process via MpControl

    The heavy YOLO inference runs in a separate OS process, bypassing
    the GIL.  The thread wrapper keeps the same put/get interface so
    the rest of the pipeline is unaware of the change
    """
    id_cnt = 0

    def __init__(self, model_name: str, stride: int, classes: list,
                 source_ids: list, roi: list, inf_params: dict,
                 queue_out: Queue):
        from evileye.core.mp_control import MpControl
        from .mp_worker_yolo import MpWorkerYolo

        self.mp_control = MpControl(
            max_input_size=max(len(roi), 2),
            name=f"det-mp-{DetectionThreadYoloMp.id_cnt}",
        )
        self.mp_worker = self.mp_control.add_worker(MpWorkerYolo)
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)
        self.mp_worker.set_params(self.model_name, self.classes, self.inf_params)
        self.mp_control.start()
        DetectionThreadYoloMp.id_cnt += 1

    def init_detection_implementation(self):
        # Model is loaded inside the child process by MpWorkerYolo.init_worker
        pass

    def predict(self, images: list):
        self.mp_control.put(images)
        res = self.mp_control.get()
        return res

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        if result is None:
            return bboxes_coords, confidences, ids
        try:
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
