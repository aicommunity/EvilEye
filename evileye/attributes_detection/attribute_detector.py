from __future__ import annotations

from typing import Any

import numpy as np

from ..core.frame import Frame
from ..core.frame_transport import SharedFrameTransport
from ..core.plugins import register_module
from ..object_detector.object_detection_base import DetectionResult, DetectionResultList


@register_module(
    "AttributeDetector",
    kind="processor_item",
    execution_modes=("thread", "process"),
    capabilities=("accepts_frame_handle", "model_class_mapping"),
    default_execution_mode="process",
)
class AttributeDetector:
    """Detect configured attributes on full frames or configured frame ROIs."""

    ResultType = DetectionResultList

    def __init__(self):
        from ..object_detector.yolo_runtime import YoloRuntime

        self._yolo_runtime = YoloRuntime()
        self._frame_transport = None
        self.enabled = True
        self.model_name = "models/y8mhardhats.pt"
        self.attrs = ["hard_hat", "no_hard_hat"]
        self.class_mapping: dict[str, int] = {}
        self.class_id_to_name: dict[int, str] = {}
        self.confidence_thresholds: dict[str, float] = {}
        self.model_confidence = 0.1
        self.inference_size = 224
        self.vid_stride = 1
        self.device = None
        self.source_ids: list[int] = []
        self.roi: list[list[list[int]]] = [[]]

    def create_state(self, config: dict[str, Any] | None, context=None):
        config = dict(config or {})
        self.enabled = bool(config.get("enabled", True))
        self.model_name = config.get("model", self.model_name)
        self.attrs = list(config.get("attrs", self.attrs) or [])
        source_ids = config.get("source_ids")
        if source_ids is None and context is not None:
            source_ids = getattr(context, "source_ids", ())
        self.source_ids = [int(value) for value in (source_ids or [])]
        self.roi = config.get("roi", self.roi) or [[]]
        self.inference_size = int(config.get("inference_size", 224))
        self.vid_stride = max(1, int(config.get("vid_stride", 1)))
        self.device = config.get("device")
        requested_threads = int(config.get("num_detection_threads", 1))
        if requested_threads != 1:
            raise ValueError(
                "AttributeDetector item runtime supports one worker per module; "
                "num_detection_threads must be 1"
            )
        base_confidence = float(config.get("conf", 0.1))
        self.confidence_thresholds = {
            str(name): float(value)
            for name, value in (config.get("confidence_thresholds") or {}).items()
        }

        configured_mapping = (
            config.get("class_mapping") or config.get("model_class_mapping") or {}
        )
        if configured_mapping:
            self.class_mapping = {
                str(name): int(class_id)
                for name, class_id in configured_mapping.items()
                if str(name) in self.attrs
            }
        else:
            self.class_mapping = {
                name: class_id for class_id, name in enumerate(self.attrs)
            }
        self.class_id_to_name = {
            class_id: name for name, class_id in self.class_mapping.items()
        }
        thresholds = [base_confidence, *self.confidence_thresholds.values()]
        self.model_confidence = min(thresholds)

        self._yolo_runtime.release()
        self._frame_transport = None
        if self.enabled:
            self._yolo_runtime.configure(
                self.model_name,
                list(self.class_id_to_name),
                {
                    "conf": self.model_confidence,
                    "imgsz": self.inference_size,
                    "half": False,
                    "device": self.device,
                    "show": bool(config.get("show", False)),
                    "save": bool(config.get("save", False)),
                },
            )
            self._yolo_runtime.load()
            if self._yolo_runtime.model is None:
                raise RuntimeError(
                    f"AttributeDetector failed to load model '{self.model_name}'"
                )
        return {"frame_counts": {}}

    def get_model_class_mapping(self) -> dict[str, int]:
        return dict(self.class_mapping)

    def _frame_image(self, frame: Frame):
        image = getattr(frame, "image", None)
        if image is not None and getattr(image, "size", 0) > 0:
            return image
        handle = getattr(frame, "frame_handle", None)
        if handle is None:
            handle = getattr(frame, "frame_ref", None)
        if handle is None:
            raise RuntimeError(
                "AttributeDetector frame has neither image nor shared-frame handle"
            )
        if self._frame_transport is None:
            self._frame_transport = SharedFrameTransport()
        image = self._frame_transport.get_frame_view(handle)
        if image is None or getattr(image, "size", 0) == 0:
            raise RuntimeError(
                f"AttributeDetector could not read shared frame {handle.shm_name}"
            )
        return image

    def _rois_for_frame(self, frame: Frame, image) -> list[tuple[int, int, int, int]]:
        height, width = image.shape[:2]
        configured_rois = self.roi
        if not isinstance(configured_rois, list) or not configured_rois:
            return [(0, 0, width, height)]
        if self.source_ids and frame.source_id in self.source_ids:
            roi_index = self.source_ids.index(frame.source_id)
        elif len(configured_rois) == 1:
            roi_index = 0
        else:
            raise ValueError(
                f"AttributeDetector has no ROI configuration for source {frame.source_id}"
            )
        source_rois = configured_rois[roi_index] if roi_index < len(configured_rois) else []
        if not source_rois:
            return [(0, 0, width, height)]

        rois = []
        for roi in source_rois:
            if len(roi) != 4:
                raise ValueError(f"AttributeDetector ROI must be [x, y, width, height]: {roi!r}")
            x, y, roi_width, roi_height = (int(value) for value in roi)
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(width, x + roi_width)
            y2 = min(height, y + roi_height)
            if x2 > x1 and y2 > y1:
                rois.append((x1, y1, x2 - x1, y2 - y1))
        return rois

    def process_item(self, item, state):
        if isinstance(item, Frame):
            frame = item
        elif isinstance(item, (tuple, list)) and len(item) >= 2:
            frame = item[1]
        else:
            raise TypeError("AttributeDetector expects Frame or (data, Frame)")
        if not isinstance(frame, Frame):
            raise TypeError("AttributeDetector input must contain a Frame")

        result = DetectionResultList()
        result.source_id = frame.source_id
        result.frame_id = frame.frame_id
        result.time_stamp = frame.time_stamp
        state = state if isinstance(state, dict) else {"frame_counts": {}}
        frame_counts = state.setdefault("frame_counts", {})
        source_id = frame.source_id
        frame_counts[source_id] = frame_counts.get(source_id, 0) + 1
        if self.enabled and (frame_counts[source_id] - 1) % self.vid_stride == 0:
            image = self._frame_image(frame)
            for x, y, width, height in self._rois_for_frame(frame, image):
                crop = np.ascontiguousarray(image[y:y + height, x:x + width])
                predictions = self._yolo_runtime.predict_raw(
                    [crop],
                    classes=list(self.class_id_to_name),
                    conf=self.model_confidence,
                    imgsz=self.inference_size,
                    device=self.device,
                )
                if predictions is None:
                    continue
                if not isinstance(predictions, list):
                    predictions = [predictions]
                if not predictions or predictions[0] is None:
                    continue
                boxes = getattr(predictions[0], "boxes", None)
                if boxes is None:
                    continue
                boxes = boxes.cpu().numpy()
                for box in boxes:
                    class_id = int(box.cls[0])
                    attr_name = self.class_id_to_name.get(class_id)
                    if attr_name is None:
                        continue
                    confidence = float(box.conf[0])
                    if confidence < self.confidence_thresholds.get(attr_name, 0.0):
                        continue
                    x1, y1, x2, y2 = box.xyxy[0].tolist()
                    detection = DetectionResult()
                    detection.bounding_box = [
                        int(x1 + x), int(y1 + y), int(x2 + x), int(y2 + y)
                    ]
                    detection.class_id = class_id
                    detection.confidence = confidence
                    detection.detection_data["attribute"] = attr_name
                    result.detections.append(detection)
        return result, frame

    def close(self):
        self._yolo_runtime.release()
        self._frame_transport = None
