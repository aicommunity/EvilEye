from queue import Queue
import threading
from .detection_thread_base import DetectionThreadBase

# Import utils later to avoid circular imports
utils = None

def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadYoloMp(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        # Import here to avoid circular imports
        from evileye.core.mp_control import MpControl
        from .mp_worker_yolo import MpWorkerYolo
        
        self.mp_control = MpControl(max_input_size=len(roi))
        self.mp_worker = self.mp_control.add_worker(MpWorkerYolo)
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)
        self.mp_worker.set_params(self.model_name, self.classes, self.inf_params)
        self.mp_control.start()

    def predict(self, images: list):
        self.mp_control.put(images)
        res = self.mp_control.get()
        return res

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if int(class_id) not in self.classes:
                continue
            utils_module = get_utils()
            abs_coords = utils_module.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids
