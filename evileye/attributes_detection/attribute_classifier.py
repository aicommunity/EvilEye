from __future__ import annotations

from typing import Any

import numpy as np

from ..core.frame import Frame
from ..core.frame_transport import SharedFrameTransport
from ..core.logger import get_module_logger
from ..core.plugins import register_module
from ..core.tracking_dto import ensure_tracking_result_list
from ..object_detector.model_class_mapping import resolve_model_class_mapping
from ..object_tracker.tracking_results import TrackingResultList


@register_module(
    "AttributeClassifier",
    kind="processor_item",
    capabilities=("accepts_frame_handle",),
    execution_modes=("thread", "process"),
    default_execution_mode="process",
)
class AttributeClassifier:
    """Classify attributes in tracker ROIs through the processor-item SPI."""

    ResultType = TrackingResultList

    def __init__(self):
        from ..object_detector.yolo_runtime import YoloRuntime

        self.logger = get_module_logger("attribute_classifier")
        self.enabled = True
        self.model_path = "models/yolo11n.pt"
        self._yolo_runtime = YoloRuntime(logger=self.logger)
        self.attrs: list[str] = []
        self.attr_class_mapping: dict[int, str] = {}
        self.conf_threshold = 0.5
        self.inference_size = 224
        self._plugin_frame_transport = None

    def create_state(self, config, context=None):
        """Load model and module state inside the selected runtime worker."""
        config = dict(config or {})
        self.enabled = bool(config.get("enabled", True))
        self.model_path = config.get("model", "models/yolo11n.pt")
        self.attrs = [str(name) for name in (config.get("attrs", []) or [])]
        self.conf_threshold = float(config.get("conf_threshold", 0.5))
        self.inference_size = int(config.get("inference_size", 224))

        class_mapping = config.get("class_mapping") or {}
        configured_mapping = {
            str(attr_name): int(class_id)
            for attr_name, class_id in class_mapping.items()
            if str(attr_name) in self.attrs
        }
        self.attr_class_mapping = {
            class_id: attr_name
            for attr_name, class_id in configured_mapping.items()
        }
        self._plugin_frame_transport = None
        self._yolo_runtime.release()
        if self.enabled:
            self._yolo_runtime.configure(
                self.model_path,
                list(self.attr_class_mapping),
                {
                    "conf": self.conf_threshold,
                    "imgsz": self.inference_size,
                    "half": False,
                },
            )
            self._yolo_runtime.load()
            if self._yolo_runtime.model is None:
                raise RuntimeError(
                    f"AttributeClassifier failed to load model '{self.model_path}'"
                )
            if not configured_mapping:
                try:
                    name_to_id = resolve_model_class_mapping(
                        self.attrs,
                        getattr(self._yolo_runtime.model, "names", None),
                        module_name=type(self).__name__,
                    )
                except Exception:
                    self._yolo_runtime.release()
                    raise
                self.attr_class_mapping = {
                    class_id: attr_name
                    for attr_name, class_id in name_to_id.items()
                }
        return self

    def _plugin_frame_image(self, frame):
        image = getattr(frame, "image", None)
        if image is not None:
            return image
        handle = getattr(frame, "frame_handle", None)
        if handle is None:
            handle = getattr(frame, "frame_ref", None)
        if handle is None:
            raise RuntimeError(
                "AttributeClassifier frame has neither image nor shared-frame handle"
            )
        if self._plugin_frame_transport is None:
            self._plugin_frame_transport = SharedFrameTransport()
        image = self._plugin_frame_transport.get_frame_view(handle)
        if image is None or getattr(image, "size", 0) == 0:
            raise RuntimeError(
                f"AttributeClassifier could not read shared frame {handle.shm_name}"
            )
        return image

    def process_item(self, item, state):
        """Attach ROI attributes to one ``(TrackingResultList, Frame)`` pair."""
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            raise TypeError("AttributeClassifier expects (tracking_data, frame)")
        tracking_data, frame = item[0], item[1]
        if not isinstance(frame, Frame):
            raise TypeError("AttributeClassifier input must contain a Frame")
        if not state.enabled:
            return (tracking_data, frame) if isinstance(item, tuple) else [tracking_data, frame]

        tracking_data = ensure_tracking_result_list(tracking_data)
        roi_data = getattr(tracking_data, "roi_data", None) or []
        if roi_data:
            image = state._plugin_frame_image(frame)
            for roi_info in roi_data:
                track_id = roi_info.get("track_id")
                roi_bbox = roi_info.get("roi_bbox")
                if track_id is None or roi_bbox is None:
                    continue
                roi_image = state._crop_roi(image, roi_bbox)
                if roi_image is None:
                    continue
                attr_results = state._classify_roi_with_detector(roi_image)
                if not hasattr(tracking_data, "attr_results"):
                    tracking_data.attr_results = {}
                tracking_data.attr_results[track_id] = attr_results

        return (tracking_data, frame) if isinstance(item, tuple) else [tracking_data, frame]

    def close(self):
        self._yolo_runtime.release()
        self._plugin_frame_transport = None

    def _classify_roi_with_detector(self, roi_image: np.ndarray) -> dict[str, dict[str, Any]]:
        if self._yolo_runtime.model is None:
            return {}
        try:
            results = self._yolo_runtime.predict_raw(
                [roi_image],
                classes=list(self.attr_class_mapping),
                conf=self.conf_threshold,
                imgsz=self.inference_size,
            )
            if results is None:
                return {}
            if not isinstance(results, list):
                results = [results]
            if not results:
                return {}
            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                return {name: {"detected_now": False, "confidence": 0.0} for name in self.attrs}

            attr_results = {
                name: {"detected_now": False, "confidence": 0.0}
                for name in self.attrs
            }
            boxes = result.boxes.cpu().numpy()
            for box in boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                attr_name = self.attr_class_mapping.get(class_id)
                if attr_name and confidence >= self.conf_threshold:
                    attr_results[attr_name] = {
                        "detected_now": True,
                        "confidence": confidence,
                        "bbox": bbox,
                        "class_id": class_id,
                    }
            return attr_results
        except Exception:
            self.logger.exception("AttributeClassifier inference failed for ROI")
            raise

    @staticmethod
    def _crop_roi(image, bbox):
        try:
            x1, y1, x2, y2 = [int(value) for value in bbox]
            roi = image[y1:y2, x1:x2]
            if roi is None or roi.size == 0:
                return None
            return roi
        except Exception:
            return None
