from queue import Queue
import threading
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


class DetectionThreadRfdetr(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        base_name = f"evileye.detection_thread_rfdetr"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
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
                
                # Update model_class_mapping from model
                self._update_model_class_mapping_from_model()
                    
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
            threshold = self.inf_params.get('conf', 0.25)
            results = self.model.predict(images, threshold=threshold)
            
            if not results:
                # Возвращаем пустой результат для каждого изображения
                return [None] * len(images)
            
            # RF-DETR возвращает объект Detections напрямую
            if hasattr(results, 'xyxy') and len(results.xyxy) > 0:
                # Фильтруем по confidence threshold
                mask = results.confidence >= threshold
                if np.any(mask):
                    # Получаем отфильтрованные данные
                    filtered_xyxy = results.xyxy[mask]
                    filtered_conf = results.confidence[mask]
                    filtered_class_ids = results.class_id[mask]
                    
                    # Округляем координаты до целых чисел и обрезаем до границ изображения
                    rounded_boxes = []
                    valid_conf = []
                    valid_class_ids = []
                    
                    # Получаем размер первого изображения (все изображения должны иметь одинаковый размер)
                    w = images[0].shape[1]
                    h = images[0].shape[0]

                    for i, bbox in enumerate(filtered_xyxy):
                        x1, y1, x2, y2 = bbox
                        # Округляем до целых чисел
                        x1 = int(round(x1))
                        y1 = int(round(y1))
                        x2 = int(round(x2))
                        y2 = int(round(y2))
                        
                        # Обрезаем до границ изображения
                        x1 = max(0, min(x1, w-1))
                        y1 = max(0, min(y1, h-1))
                        x2 = max(0, min(x2, w-1))
                        y2 = max(0, min(y2, h-1))
                        
                        # Проверяем, что после округления и обрезки есть ненулевая ширина и высота
                        if x1 < x2 and y1 < y2:
                            rounded_bbox = np.array([x1, y1, x2, y2], dtype=np.int32)
                            rounded_boxes.append(rounded_bbox)
                            valid_conf.append(filtered_conf[i])
                            valid_class_ids.append(filtered_class_ids[i])
                    
                    if rounded_boxes:
                        from supervision import Detections
                        combined_result = Detections(
                            xyxy=np.array(rounded_boxes, dtype=np.int32),
                            confidence=np.array(valid_conf),
                            class_id=np.array(valid_class_ids)
                        )
                        # Возвращаем результат для каждого изображения
                        return [combined_result] * len(images)
                    else:
                        # Возвращаем пустой результат для каждого изображения
                        return [None] * len(images)
                
                return [None] * len(images)
            else:
                return [None] * len(images)
                
        except Exception as e:
            return [None] * len(images)

    def get_bboxes(self, result, roi):
        """
        Извлекает bounding boxes, confidence scores и class IDs из результата RF-DETR
        """
        bboxes_coords = []
        confidences = []
        ids = []
        
        try:
            # Проверяем, что result не None
            if result is None:
                return bboxes_coords, confidences, ids
                
            # RF-DETR возвращает объект supervision.Detections
            if hasattr(result, 'xyxy') and hasattr(result, 'confidence') and hasattr(result, 'class_id'):
                coords = result.xyxy
                confs = result.confidence
                class_ids = result.class_id
                
                for coord, class_id, conf in zip(coords, class_ids, confs):
                    if int(class_id) not in self.classes:
                        continue
                    utils_module = get_utils()
                    abs_coords = utils_module.roi_to_image(coord, roi[1][0], roi[1][1])
                    bboxes_coords.append(abs_coords)
                    confidences.append(conf)
                    ids.append(class_id)
                
        except Exception as e:
            pass
            
        return bboxes_coords, confidences, ids
    
    def _update_model_class_mapping_from_model(self):
        """Update model_class_mapping from RFDETR model names"""
        if self.model and hasattr(self.model, 'class_names'):
            # RFDETR uses class_names attribute
            class_names = self.model.class_names
            if class_names:
                # Create mapping from model names: {class_name: class_id}
                self.model_class_mapping = {name: idx for idx, name in enumerate(class_names)}
                self.logger.info(f"Updated model_class_mapping from RFDETR model: {self.model_class_mapping}")
        elif self.model and hasattr(self.model, 'names'):
            # Fallback to names attribute if available
            self.model_class_mapping = {name: idx for idx, name in self.model.names.items()}
            self.logger.info(f"Updated model_class_mapping from RFDETR model (names): {self.model_class_mapping}")