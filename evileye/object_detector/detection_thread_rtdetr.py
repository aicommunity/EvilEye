from queue import Queue
import threading
from ultralytics import RTDETR
from .detection_thread_base import DetectionThreadBase
import logging

# Import utils later to avoid circular imports
utils = None

def get_utils():
    global utils
    if utils is None:
        from evileye.utils import utils as utils_module
        utils = utils_module
    return utils


class DetectionThreadRtdetr(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        base_name = f"evileye.detection_thread_rtdetr"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.model_name = model_name
        self.model = None
        self.original_image_size = None  # Инициализируем размер изображения
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self):
        if self.model is None:
            self.model = RTDETR(self.model_name)
            self.model.fuse()  # Fuse Conv+BN layers
            if self.inf_params.get('half', True):
                self.model.half()
            self.logger.info(f"Model names: {self.model.names}")
            
            # Update model_class_mapping from model
            self._update_model_class_mapping_from_model()

    def predict(self, images: list):
        # Defer classes filtering to base; avoid passing names to model
        return self.model.predict(source=images, classes=self._get_classes_arg_for_model(), verbose=False, **self.inf_params)

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        
        # Получаем размер исходного изображения из roi (roi содержит информацию об изображении)
        img_width = result.orig_img.shape[1]
        img_height = result.orig_img.shape[0]
        
        for coord, class_id, conf in zip(coords, class_ids, confs):
            # Преобразуем координаты в целые числа
            x1, y1, x2, y2 = coord
            x1 = int(round(x1))
            y1 = int(round(y1))
            x2 = int(round(x2))
            y2 = int(round(y2))
            
            # Ограничиваем координаты границами исходного изображения
            x1 = max(0, min(x1, img_width - 1))
            y1 = max(0, min(y1, img_height - 1))
            x2 = max(0, min(x2, img_width - 1))
            y2 = max(0, min(y2, img_height - 1))
            
            # Проверяем, что координаты валидны после ограничения
            if x1 < x2 and y1 < y2:
                utils_module = get_utils()
                # Проверяем, что ROI существует
                if len(roi) > 1 and len(roi[1]) > 1:
                    abs_coords = utils_module.roi_to_image([x1, y1, x2, y2], roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
                else:
                    # Если ROI не определен, используем координаты как есть
                    abs_coords = [x1, y1, x2, y2]
                bboxes_coords.append(abs_coords)
                confidences.append(conf)
                ids.append(class_id)
        return bboxes_coords, confidences, ids
    
    def _update_model_class_mapping_from_model(self):
        """Update model_class_mapping from RTDETR model names"""
        if self.model and hasattr(self.model, 'names') and self.model.names:
            # Create mapping from model names: {class_name: class_id}
            self.model_class_mapping = {name: idx for idx, name in self.model.names.items()}
            self.logger.info(f"Updated model_class_mapping from RTDETR model: {self.model_class_mapping}")
