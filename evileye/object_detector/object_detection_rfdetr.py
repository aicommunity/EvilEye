from .object_detection_base import ModelBasedDetectorBase
from ..core.plugins import register_module
from ..core.logger import get_module_logger
from .object_detection_yolo import ObjectDetectorYolo

_logger = get_module_logger("object_detection_rfdetr")
_SUPPORT_RFDETR = True
try:
    import torch
    from packaging import version

    if version.parse(getattr(torch, "__version__", "0.0.0")) < version.parse("2.2.0"):
        _logger.info("RF-DETR disabled: requires torch>=2.2.0")
        _SUPPORT_RFDETR = False
except Exception:
    _logger.info("RF-DETR disabled: PyTorch is not available")
    _SUPPORT_RFDETR = False


class ObjectDetectorRfdetr(ObjectDetectorYolo):
    """RF-DETR item processor with native Supervision result handling."""

    def __init__(self):
        super().__init__()
        self.model_name = self._get_default_model_name()

    def _create_plugin_runtime(self):
        from .rfdetr_runtime import RfdetrRuntime

        return RfdetrRuntime(logger=self.logger)

    def _get_detection_thread_type(self) -> str:
        return "rfdetr"

    def _get_default_model_name(self) -> str:
        return "rfdetr-nano"

    def _resolve_model_path(self, model_name: str) -> str:
        return model_name

    def _plugin_model_mapping(self, model):
        names = getattr(model, "class_names", None)
        if isinstance(names, dict):
            if all(isinstance(value, int) for value in names.values()):
                return {str(name): int(class_id) for name, class_id in names.items()}
            return {str(name): int(class_id) for class_id, name in names.items()}
        if isinstance(names, (list, tuple)):
            return {str(name): class_id for class_id, name in enumerate(names)}
        return super()._plugin_model_mapping(model)

    def _plugin_roi_detections(self, crops, rois):
        from ..utils import utils

        predictions = self._plugin_model_runtime.predict_raw(crops)
        if not isinstance(predictions, list) or len(predictions) != len(crops):
            raise RuntimeError("RF-DETR runtime returned an invalid batch result")
        boxes, confidences, class_ids = [], [], []
        for crop, roi, prediction in zip(crops, rois, predictions):
            if prediction is None:
                raise RuntimeError("RF-DETR returned no result for an input image")
            if not all(
                hasattr(prediction, field)
                for field in ("xyxy", "confidence", "class_id")
            ):
                raise TypeError("RF-DETR result must expose xyxy, confidence, and class_id")
            height, width = crop.shape[:2]
            for bbox, confidence, raw_class_id in zip(
                prediction.xyxy, prediction.confidence, prediction.class_id
            ):
                class_id = int(raw_class_id)
                if (
                    self._plugin_class_filter is not None
                    and class_id not in self._plugin_class_filter
                ):
                    continue
                confidence = float(confidence)
                if confidence < self._plugin_confidence:
                    continue
                x1, y1, x2, y2 = (
                    int(round(float(value))) for value in bbox
                )
                x1 = max(0, min(x1, width - 1))
                y1 = max(0, min(y1, height - 1))
                x2 = max(0, min(x2, width - 1))
                y2 = max(0, min(y2, height - 1))
                if x1 >= x2 or y1 >= y2:
                    continue
                boxes.append(utils.roi_to_image([x1, y1, x2, y2], roi[0], roi[1]))
                confidences.append(confidence)
                class_ids.append(class_id)
        if boxes:
            boxes, confidences, class_ids = utils.non_max_sup(
                boxes, confidences, class_ids
            )
        return boxes, confidences, class_ids

    def init_impl(self):
        return ModelBasedDetectorBase.init_impl(self)


if _SUPPORT_RFDETR:
    ObjectDetectorRfdetr = register_module(
        "ObjectDetectorRfdetr",
        kind="processor_item",
        capabilities=(
            "accepts_frame_handle",
            "model_class_mapping",
            "parallel_items",
        ),
        execution_modes=("thread", "process"),
        default_execution_mode="process",
    )(ObjectDetectorRfdetr)
else:
    _logger.info("ObjectDetectorRfdetr not registered due to environment constraints")
