from queue import Queue
from typing import Optional
import logging
import os
import platform
import sys

from .detection_thread_base import DetectionThreadBase
from .yolo_runtime import YoloRuntime


class DetectionThreadYolo(DetectionThreadBase):
    """Detection thread for YOLO models."""

    def __init__(
            self,
            model_name: str,
            stride: int,
            classes: list,
            source_ids: list,
            roi: list,
            inf_params: dict,
            queue_out: Queue,
            logger_name: Optional[str] = None,
            parent_logger: Optional[logging.Logger] = None,
    ):
        base_name = "evileye.detection_thread_yolo"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.model_name = model_name
        self._yolo_runtime: YoloRuntime = YoloRuntime(logger=self.logger)
        self._yolo_runtime.configure(model_name, classes, inf_params)
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    @property
    def model(self):
        """Ultralytics model handle (thread path class mapping)."""
        return self._yolo_runtime.model

    @model.setter
    def model(self, value) -> None:
        self._yolo_runtime.model = value

    def init_detection_implementation(self) -> None:
        if not self.run_flag:
            return
        if self._yolo_runtime.model is not None:
            return
        try:
            model_path = self.model_name
            model_exists = os.path.exists(model_path) if model_path else False
            model_size = os.path.getsize(model_path) if model_exists else 0
            self.logger.debug(f"Loading YOLO model: {model_path}")
            self.logger.debug(
                f"Model file exists: {model_exists}, size: {model_size} bytes, "
                f"platform: {platform.system()} {platform.release()}"
            )
            self._yolo_runtime.configure(
                self.model_name, self.classes, self.inf_params
            )
            self._yolo_runtime.load()
            if self._yolo_runtime.model is not None:
                self.logger.debug(
                    "Model loaded successfully. Model names: %s",
                    self._yolo_runtime.model.names,
                )
                self._update_model_class_mapping_from_model()
        except RuntimeError as e:
            error_msg = str(e)
            error_context = {
                "error_type": "RuntimeError",
                "error_message": error_msg,
                "model_path": self.model_name,
                "model_exists": os.path.exists(self.model_name) if self.model_name else False,
                "platform": f"{platform.system()} {platform.release()}",
                "python_version": sys.version.split()[0],
            }
            if "zip archive" in error_msg.lower() or "central directory" in error_msg.lower():
                self.logger.error(
                    "Model file appears to be corrupted (ZIP archive error): %s",
                    self.model_name,
                )
            else:
                self.logger.error("Failed to load YOLO model: %s", error_msg)
            self.logger.debug("Model loading context: %s", error_context)
            self.logger.warning(
                "Model will not be loaded. Detection will be disabled for this thread."
            )
            self._yolo_runtime.release()
        except FileNotFoundError as e:
            self.logger.error("Model file not found: %s", self.model_name)
            self.logger.error("Error: %s", e)
            self.logger.warning(
                "Model will not be loaded. Detection will be disabled for this thread."
            )
            self._yolo_runtime.release()
        except Exception as e:
            self.logger.error("Unexpected error loading YOLO model: %s", e)
            self.logger.debug("Model loading context", exc_info=True)
            self.logger.warning(
                "Model will not be loaded. Detection will be disabled for this thread."
            )
            self._yolo_runtime.release()

    def predict(self, images: list) -> list:
        if self._yolo_runtime.model is None:
            self.logger.warning(
                "Model is not loaded, cannot perform prediction. Returning empty results."
            )
            return [None] * len(images) if isinstance(images, list) else None

        if not isinstance(images, list):
            self.logger.warning("Expected list of images, got %s", type(images))
            return None

        valid_images = []
        image_indices = []
        for i, img in enumerate(images):
            if img is not None:
                valid_images.append(img)
                image_indices.append(i)

        if len(valid_images) == 0:
            self.logger.warning("All images are None, cannot perform prediction")
            return [None] * len(images)

        try:
            results = self._yolo_runtime.predict_raw(
                valid_images,
                classes=self._get_classes_arg_for_model(),
            )
            if results is None:
                return [None] * len(images)
            if not isinstance(results, list):
                results = [results]
            full_results = [None] * len(images)
            for idx, result_idx in enumerate(image_indices):
                if idx < len(results):
                    full_results[result_idx] = results[idx]
            return full_results
        except Exception as e:
            self.logger.error("Error during model prediction: %s", e)
            self.logger.debug("Prediction error details", exc_info=True)
            return [None] * len(images)

    def get_bboxes(self, result, roi: list) -> tuple[list, list, list]:
        if result is None:
            self.logger.debug("Prediction result is None, returning empty bboxes")
            return [], [], []
        from .bbox_utils import roi_boxes_to_image_coords

        try:
            return roi_boxes_to_image_coords(
                result, (roi[1][0], roi[1][1]), logger=self.logger
            )
        except AttributeError as e:
            self.logger.warning(
                "Result does not have 'boxes' attribute: %s. Returning empty bboxes.", e
            )
            return [], [], []
        except Exception as e:
            self.logger.error("Error extracting bboxes from result: %s", e)
            self.logger.debug("Bbox extraction error details", exc_info=True)
            return [], [], []

    def _release_model(self) -> None:
        self._yolo_runtime.release()

    def stop(self) -> None:
        super().stop()
        self._release_model()

    def _update_model_class_mapping_from_model(self):
        """Update model_class_mapping from YOLO model names."""
        model = self._yolo_runtime.model
        if model and hasattr(model, "names") and model.names:
            self.model_class_mapping = {name: idx for idx, name in model.names.items()}
            self.logger.debug(
                "Updated model_class_mapping from YOLO model: %s",
                self.model_class_mapping,
            )
