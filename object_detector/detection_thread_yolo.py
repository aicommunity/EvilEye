from queue import Queue
import threading
from ultralytics import YOLO
from object_detector.detection_thread_base import DetectionThreadBase
from utils import utils


class DetectionThreadYolo(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self):
        if self.model is None:
            self.model = YOLO(self.model_name)

    def predict(self, images: list):
        return self.model.predict(source=images, classes=self.classes, verbose=False, **self.inf_params)

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        for coord, class_id, conf in zip(coords, class_ids, confs):
            if int(class_id) not in self.classes:
                continue
            abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
            bboxes_coords.append(abs_coords)
            confidences.append(conf)
            ids.append(class_id)
        return bboxes_coords, confidences, ids
