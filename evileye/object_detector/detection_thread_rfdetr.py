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


class DetectionThreadRfdetr(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self):
        if self.model is None:
            try:
                from rfdetr import RFDETRNano, RFDETRSmall, RFDETRMedium, RFDETRLarge
                
                # Выбираем модель в зависимости от имени
                if "nano" in self.model_name.lower():
                    self.model = RFDETRNano()
                elif "small" in self.model_name.lower():
                    self.model = RFDETRSmall()
                elif "medium" in self.model_name.lower():
                    self.model = RFDETRMedium()
                elif "large" in self.model_name.lower():
                    self.model = RFDETRLarge()
                else:
                    # По умолчанию используем nano
                    self.model = RFDETRNano()

                self.model.optimize_for_inference()
                    
            except ImportError:
                raise ImportError("RF-DETR package not installed. Please install it using: pip install rfdetr")
            except Exception as e:
                raise Exception(f"Failed to initialize RF-DETR model: {e}")

    def predict(self, images: list):
        """
        Выполняет предсказание для списка изображений
        """
        if self.model is None:
            raise RuntimeError("Model not initialized")
        
        try:
            # RF-DETR принимает список изображений и возвращает результаты
            results = self.model.predict(images, conf=self.inf_params.get('conf', 0.25))
            return results
        except Exception as e:
            print(f"Error during RF-DETR prediction: {e}")
            return []

    def get_bboxes(self, result, roi):
        """
        Извлекает bounding boxes, confidence scores и class IDs из результата RF-DETR
        """
        bboxes_coords = []
        confidences = []
        ids = []
        
        try:
            # RF-DETR возвращает объект supervision.Detections
            if hasattr(result, 'xyxy') and hasattr(result, 'confidence') and hasattr(result, 'class_id'):
                # Получаем данные из объекта Detections
                coords = result.xyxy
                confs = result.confidence
                class_ids = result.class_id
                
                # Проверяем, что есть детекции
                if len(coords) > 0:
                    for coord, class_id, conf in zip(coords, class_ids, confs):
                        if int(class_id) not in self.classes:
                            continue
                        utils_module = get_utils()
                        abs_coords = utils_module.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
                        bboxes_coords.append(abs_coords)
                        confidences.append(conf)
                        ids.append(class_id)
            else:
                print("RF-DETR result does not have expected attributes (xyxy, confidence, class_id)")
                
        except Exception as e:
            print(f"Error extracting bboxes from RF-DETR result: {e}")
            
        return bboxes_coords, confidences, ids
