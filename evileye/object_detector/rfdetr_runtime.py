"""RF-DETR model lifecycle for plugin item workers."""

from __future__ import annotations

import logging


class RfdetrRuntime:
    """Load one RF-DETR variant and return one Supervision result per image."""

    _MODEL_CLASSES = {
        "nano": "RFDETRNano",
        "small": "RFDETRSmall",
        "medium": "RFDETRMedium",
        "large": "RFDETRLarge",
    }

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("evileye.rfdetr_runtime")
        self.model_name = ""
        self.model = None
        self.classes = []
        self.inf_params = {}

    def configure(self, model_name, classes, inf_params):
        self.model_name = str(model_name)
        self.classes = list(classes or [])
        self.inf_params = dict(inf_params or {})

    def load(self):
        if self.model is not None:
            return
        normalized = self.model_name.strip().lower().replace("_", "-")
        for prefix in ("rfdetr-", "rf-detr-"):
            if normalized.startswith(prefix):
                normalized = normalized[len(prefix):]
                break
        class_name = self._MODEL_CLASSES.get(normalized)
        if class_name is None:
            supported = ", ".join(sorted(self._MODEL_CLASSES))
            raise ValueError(
                f"Unsupported RF-DETR model '{self.model_name}'; expected one of: {supported}"
            )
        from rfdetr import RFDETRLarge, RFDETRMedium, RFDETRNano, RFDETRSmall

        model_class = {
            "RFDETRNano": RFDETRNano,
            "RFDETRSmall": RFDETRSmall,
            "RFDETRMedium": RFDETRMedium,
            "RFDETRLarge": RFDETRLarge,
        }[class_name]
        self.model = model_class(
            resolution=int(self.inf_params.get("imgsz", 640))
        )
        self.model.optimize_for_inference()

    def predict_raw(self, images, *, classes=None, **kwargs):
        if self.model is None:
            raise RuntimeError("RF-DETR runtime is not loaded")
        if not images:
            return []
        results = self.model.predict(
            images,
            threshold=float(self.inf_params.get("conf", 0.25)),
        )
        if isinstance(results, list):
            if len(results) != len(images):
                raise RuntimeError(
                    f"RF-DETR returned {len(results)} results for {len(images)} images"
                )
            return results
        if len(images) == 1:
            return [results]
        raise RuntimeError(
            "RF-DETR must return one result per image for batched ROI inference"
        )

    def release(self):
        self.model = None
