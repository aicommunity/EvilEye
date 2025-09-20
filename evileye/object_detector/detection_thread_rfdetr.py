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
            
            # Если это список результатов, объединяем их
            if isinstance(results, list):
                # Находим непустые результаты
                non_empty_results = [r for r in results if hasattr(r, 'xyxy') and len(r.xyxy) > 0]
                if non_empty_results:
                    # Объединяем все непустые детекции в один результат
                    from supervision import Detections
                    all_xyxy = []
                    all_conf = []
                    all_class_ids = []
                    
                    for result in non_empty_results:
                        if hasattr(result, 'xyxy') and len(result.xyxy) > 0:
                            # Фильтруем по confidence threshold
                            mask = result.confidence >= threshold
                            if np.any(mask):
                                all_xyxy.append(result.xyxy[mask])
                                all_conf.append(result.confidence[mask])
                                all_class_ids.append(result.class_id[mask])
                    
                    if all_xyxy:
                        import numpy as np
                        combined_result = Detections(
                            xyxy=np.vstack(all_xyxy),
                            confidence=np.hstack(all_conf),
                            class_id=np.hstack(all_class_ids)
                        )
                        return [combined_result]
                return []
            else:
                # Если это не список, возвращаем как есть
                return [results]
                
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
