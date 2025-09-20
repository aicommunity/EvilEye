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
                
                # Получаем параметры из inf_params
                # RF-DETR использует inference_size из конфигурации
                resolution = self.inf_params.get('inference_size', 640)
                
                # Выбираем модель в зависимости от имени
                if "nano" in self.model_name.lower():
                    self.model = RFDETRNano(resolution=resolution)
                elif "small" in self.model_name.lower():
                    self.model = RFDETRSmall(resolution=resolution)
                elif "medium" in self.model_name.lower():
                    self.model = RFDETRMedium(resolution=resolution)
                elif "large" in self.model_name.lower():
                    self.model = RFDETRLarge(resolution=resolution)
                else:
                    # По умолчанию используем nano
                    self.model = RFDETRNano(resolution=resolution)

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
            import numpy as np
            # RF-DETR принимает список изображений и возвращает результаты
            # Используем threshold вместо conf для RF-DETR
            threshold = self.inf_params.get('conf', 0.25)
            results = self.model.predict(images, threshold=threshold)
            
            # RF-DETR возвращает список результатов, нужно объединить все непустые детекции
            if not results:
                return []
            
            # RF-DETR возвращает объект Detections напрямую
            if hasattr(results, 'xyxy') and len(results.xyxy) > 0:
                # Фильтруем по confidence threshold
                mask = results.confidence >= threshold
                if np.any(mask):
                    # Получаем отфильтрованные данные
                    filtered_xyxy = results.xyxy[mask]
                    filtered_conf = results.confidence[mask]
                    filtered_class_ids = results.class_id[mask]
                    
                    # Дополнительная фильтрация некорректных bounding boxes и округление
                    valid_boxes = []
                    valid_conf = []
                    valid_class_ids = []
                    
                    # Получаем размер изображения из параметров
                    img_size = self.inf_params.get('inference_size', 640)
                    
                    for i, bbox in enumerate(filtered_xyxy):
                        x1, y1, x2, y2 = bbox
                        
                        # Округляем координаты до целых чисел
                        x1 = int(round(x1))
                        y1 = int(round(y1))
                        x2 = int(round(x2))
                        y2 = int(round(y2))
                        
                        width = x2 - x1
                        height = y2 - y1
                        
                        # Проверяем на проблемы
                        issues = []
                        if width <= 0 or height <= 0:
                            issues.append('zero/negative size')
                        if x1 < 0 or y1 < 0 or x2 > img_size or y2 > img_size:
                            issues.append('out of bounds')
                        if x1 >= x2 or y1 >= y2:
                            issues.append('invalid coordinates')
                        if width > img_size or height > img_size:
                            issues.append('too large')
                        
                        if not issues:
                            # Создаем новый bbox с целочисленными координатами
                            rounded_bbox = np.array([x1, y1, x2, y2], dtype=np.int32)
                            valid_boxes.append(rounded_bbox)
                            valid_conf.append(filtered_conf[i])
                            valid_class_ids.append(filtered_class_ids[i])
                    
                    if valid_boxes:
                        from supervision import Detections
                        combined_result = Detections(
                            xyxy=np.array(valid_boxes, dtype=np.int32),
                            confidence=np.array(valid_conf),
                            class_id=np.array(valid_class_ids)
                        )
                        return [combined_result]
                
                return []
            else:
                return []
                
        except Exception as e:
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
                pass
                
        except Exception as e:
            pass
            
        return bboxes_coords, confidences, ids
