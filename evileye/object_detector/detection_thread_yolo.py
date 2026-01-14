from queue import Queue
import threading
from ultralytics import YOLO
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


class DetectionThreadYolo(DetectionThreadBase):
    id_cnt = 0  # Переменная для присвоения каждому детектору своего идентификатора

    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue, logger_name: str | None = None, parent_logger: logging.Logger | None = None):
        base_name = f"evileye.detection_thread_yolo"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self):
        import os
        import platform
        import sys
        
        if self.model is None:
            try:
                # Логируем контекст загрузки модели
                model_path = self.model_name
                model_exists = os.path.exists(model_path) if model_path else False
                model_size = os.path.getsize(model_path) if model_exists else 0
                
                self.logger.info(f"Loading YOLO model: {model_path}")
                self.logger.debug(f"Model file exists: {model_exists}, size: {model_size} bytes, "
                                f"platform: {platform.system()} {platform.release()}")
                
                # Попытка загрузки модели
                self.model = YOLO(self.model_name)
                
                # Try to fuse Conv+BN layers (optimization, not required)
                try:
                    self.model.fuse()  # Fuse Conv+BN layers
                except Exception as e:
                    # Fuse may fail with mixed precision models, continue without it
                    self.logger.debug(f"Model fuse() failed (non-critical): {e}")
                
                # Применение half precision если требуется
                try:
                    if self.inf_params.get('half', True):
                        self.model.half()
                except Exception as e:
                    self.logger.warning(f"Failed to apply half precision to model (non-critical): {e}")
                
                self.logger.info(f"Model loaded successfully. Model names: {self.model.names}")
                
                # Update model_class_mapping from model
                self._update_model_class_mapping_from_model()
                
            except RuntimeError as e:
                # Обработка ошибок загрузки модели (поврежденный файл, проблемы с ZIP архивом и т.д.)
                error_msg = str(e)
                error_context = {
                    'error_type': 'RuntimeError',
                    'error_message': error_msg,
                    'model_path': self.model_name,
                    'model_exists': os.path.exists(self.model_name) if self.model_name else False,
                    'platform': f"{platform.system()} {platform.release()}",
                    'python_version': sys.version.split()[0]
                }
                
                if 'zip archive' in error_msg.lower() or 'central directory' in error_msg.lower():
                    self.logger.error(f"Model file appears to be corrupted (ZIP archive error): {self.model_name}")
                    self.logger.error(f"Error details: {error_msg}")
                    self.logger.debug(f"Model loading context: {error_context}")
                    self.logger.warning("Model will not be loaded. Detection will be disabled for this thread. "
                                      "Please check the model file or re-download it.")
                else:
                    self.logger.error(f"Failed to load YOLO model: {error_msg}")
                    self.logger.debug(f"Model loading context: {error_context}")
                
                # Устанавливаем модель в None, чтобы поток мог продолжать работу без модели
                self.model = None
                # Не пробрасываем исключение дальше - поток продолжит работу
                
            except FileNotFoundError as e:
                # Обработка ошибки отсутствия файла модели
                self.logger.error(f"Model file not found: {self.model_name}")
                self.logger.error(f"Error: {e}")
                self.logger.warning("Model will not be loaded. Detection will be disabled for this thread.")
                self.model = None
                # Не пробрасываем исключение дальше
                
            except Exception as e:
                # Обработка любых других ошибок загрузки модели
                error_context = {
                    'error_type': type(e).__name__,
                    'error_message': str(e),
                    'model_path': self.model_name,
                    'model_exists': os.path.exists(self.model_name) if self.model_name else False,
                    'platform': f"{platform.system()} {platform.release()}",
                    'python_version': sys.version.split()[0]
                }
                
                self.logger.error(f"Unexpected error loading YOLO model: {e}")
                self.logger.debug(f"Model loading context: {error_context}", exc_info=True)
                self.logger.warning("Model will not be loaded. Detection will be disabled for this thread.")
                self.model = None
                # Не пробрасываем исключение дальше

    def predict(self, images: list):
        # Проверяем, что модель загружена
        if self.model is None:
            self.logger.warning("Model is not loaded, cannot perform prediction. Returning empty results.")
            # Возвращаем пустой список результатов для каждого изображения
            return [None] * len(images) if isinstance(images, list) else None
        
        try:
            # Defer classes filtering to base; avoid passing names to model
            return self.model.predict(source=images, classes=self._get_classes_arg_for_model(), verbose=False, **self.inf_params)
        except Exception as e:
            self.logger.error(f"Error during model prediction: {e}")
            self.logger.debug("Prediction error details", exc_info=True)
            # Возвращаем пустой список результатов для каждого изображения
            return [None] * len(images) if isinstance(images, list) else None

    def get_bboxes(self, result, roi):
        bboxes_coords = []
        confidences = []
        ids = []
        
        # Обработка случая, когда результат None (модель не загружена или ошибка предсказания)
        if result is None:
            self.logger.debug("Prediction result is None, returning empty bboxes")
            return bboxes_coords, confidences, ids
        
        try:
            boxes = result.boxes.cpu().numpy()
            coords = boxes.xyxy
            confs = boxes.conf
            class_ids = boxes.cls
            
            for coord, class_id, conf in zip(coords, class_ids, confs):
                utils_module = get_utils()
                abs_coords = utils_module.roi_to_image(coord, roi[1][0], roi[1][1])  # Получаем координаты рамки в СК всего изображения
                bboxes_coords.append(abs_coords)
                confidences.append(conf)
                ids.append(class_id)
        except AttributeError as e:
            # Обработка случая, когда у результата нет атрибута boxes
            self.logger.warning(f"Result does not have 'boxes' attribute: {e}. Returning empty bboxes.")
        except Exception as e:
            # Обработка любых других ошибок при извлечении bboxes
            self.logger.error(f"Error extracting bboxes from result: {e}")
            self.logger.debug("Bbox extraction error details", exc_info=True)
        
        return bboxes_coords, confidences, ids
    
    def _update_model_class_mapping_from_model(self):
        """Update model_class_mapping from YOLO model names"""
        if self.model and hasattr(self.model, 'names') and self.model.names:
            # Create mapping from model names: {class_name: class_id}
            self.model_class_mapping = {name: idx for idx, name in self.model.names.items()}
            self.logger.info(f"Updated model_class_mapping from YOLO model: {self.model_class_mapping}")
