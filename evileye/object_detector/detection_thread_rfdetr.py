from queue import Queue
import threading
from typing import Optional
from .detection_thread_base import DetectionThreadBase
import logging


class DetectionThreadRfdetr(DetectionThreadBase):
    """Detection thread for RF-DETR models."""

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
        base_name = f"evileye.detection_thread_rfdetr"
        full_name = f"{base_name}.{logger_name}" if logger_name else base_name
        self.logger = parent_logger or logging.getLogger(full_name)
        self.model_name = model_name
        self.model = None
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self) -> None:
        if self.model is None:
            try:
                from rfdetr import RFDETRNano, RFDETRSmall, RFDETRMedium, RFDETRLarge

                # Get parameters from inf_params
                # RF-DETR uses inference_size from configuration
                resolution = self.inf_params.get('inference_size', 640)

                # Select model based on name
                if "nano" in self.model_name.lower():
                    self.model = RFDETRNano(resolution=resolution)
                elif "small" in self.model_name.lower():
                    self.model = RFDETRSmall(resolution=resolution)
                elif "medium" in self.model_name.lower():
                    self.model = RFDETRMedium(resolution=resolution)
                elif "large" in self.model_name.lower():
                    self.model = RFDETRLarge(resolution=resolution)
                else:
                    # Default to nano
                    self.model = RFDETRNano(resolution=resolution)

                self.model.optimize_for_inference()

                # Update model_class_mapping from model
                self._update_model_class_mapping_from_model()

            except ImportError:
                raise ImportError("RF-DETR package not installed. Please install it using: pip install rfdetr")
            except Exception as e:
                raise Exception(f"Failed to initialize RF-DETR model: {e}")

    def predict(self, images: list) -> list:
        """
        Run prediction on a list of images.
        """
        if self.model is None:
            raise RuntimeError("Model not initialized")

        try:
            import numpy as np
            # RF-DETR accepts list of images and returns results
            threshold = self.inf_params.get('conf', 0.25)
            results = self.model.predict(images, threshold=threshold)

            if not results:
                # Return empty result for each image
                return [None] * len(images)

            # RF-DETR returns Detections object directly
            if hasattr(results, 'xyxy') and len(results.xyxy) > 0:
                # Filter by confidence threshold
                mask = results.confidence >= threshold
                if np.any(mask):
                    # Get filtered data
                    filtered_xyxy = results.xyxy[mask]
                    filtered_conf = results.confidence[mask]
                    filtered_class_ids = results.class_id[mask]

                    # Round coordinates to integers and clip to image boundaries
                    rounded_boxes = []
                    valid_conf = []
                    valid_class_ids = []

                    # Get size of first image (all images should have same size)
                    w = images[0].shape[1]
                    h = images[0].shape[0]

                    for i, bbox in enumerate(filtered_xyxy):
                        x1, y1, x2, y2 = bbox
                        # Round to integers
                        x1 = int(round(x1))
                        y1 = int(round(y1))
                        x2 = int(round(x2))
                        y2 = int(round(y2))

                        # Clip to image boundaries
                        x1 = max(0, min(x1, w - 1))
                        y1 = max(0, min(y1, h - 1))
                        x2 = max(0, min(x2, w - 1))
                        y2 = max(0, min(y2, h - 1))

                        # Check that after rounding and clipping there is non-zero width and height
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
                        # Return result for each image
                        return [combined_result] * len(images)
                    else:
                        # Return empty result for each image
                        return [None] * len(images)

                return [None] * len(images)
            else:
                return [None] * len(images)

        except Exception as e:
            return [None] * len(images)

    def get_bboxes(self, result, roi: list) -> tuple[list, list, list]:
        """
        Extract bounding boxes, confidence scores and class IDs from RF-DETR result.
        """
        bboxes_coords = []
        confidences = []
        ids = []

        try:
            # Check that result is not None
            if result is None:
                return bboxes_coords, confidences, ids

            # RF-DETR returns supervision.Detections object
            if hasattr(result, 'xyxy') and hasattr(result, 'confidence') and hasattr(result, 'class_id'):
                coords = result.xyxy
                confs = result.confidence
                class_ids = result.class_id

                for coord, class_id, conf in zip(coords, class_ids, confs):
                    if int(class_id) not in self.classes:
                        continue
                    from ..utils import utils
                    abs_coords = utils.roi_to_image(coord, roi[1][0], roi[1][1])
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
