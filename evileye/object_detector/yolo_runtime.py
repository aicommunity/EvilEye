"""Centralized YOLO load/predict for thread and MP workers."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ultralytics import YOLO

from ..core.gpu_errors import CudaOutOfMemoryError, is_cuda_oom_error
from .ultralytics_postprocess import apply_ultralytics_optimizations


class YoloRuntime:
    """Owns a single Ultralytics YOLO model instance."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._logger = logger or logging.getLogger("evileye.yolo_runtime")
        self.model_name: str = ""
        self.model: Any = None
        self.classes: list = []
        self.inf_params: dict = {}

    def configure(self, model_name: str, classes: list, inf_params: dict) -> None:
        self.model_name = model_name
        self.classes = list(classes or [])
        self.inf_params = dict(inf_params or {})

    def load(self) -> None:
        if self.model is not None:
            return
        model_path = self.model_name
        if model_path and not Path(str(model_path)).is_absolute():
            model_path = str((Path.cwd() / model_path).resolve())
        try:
            self.model = YOLO(model_path)
            apply_ultralytics_optimizations(
                self.model,
                half=bool(self.inf_params.get("half", True)),
                logger=self._logger,
            )
        except Exception as exc:
            if is_cuda_oom_error(exc):
                raise CudaOutOfMemoryError(
                    f"Failed to load YOLO model on CUDA: {model_path}: {exc}"
                ) from exc
            raise

    def predict(self, images: list) -> list:
        """MP worker path: Ultralytics predict → DTO dict lists per image."""
        results = self.predict_raw(images, classes=self.classes)
        if results is None:
            return [[] for _ in images]
        if not isinstance(results, list):
            results = [results]
        return yolo_results_to_dto_list(results)

    def predict_raw(
        self,
        images: list,
        *,
        classes: list | None = None,
        **predict_kwargs: Any,
    ) -> list | Any | None:
        """Thread path: return native Ultralytics Results (for get_bboxes)."""
        if self.model is None:
            self.load()
        if self.model is None:
            return None
        params = dict(self.inf_params)
        params.update(predict_kwargs)
        cls = self.classes if classes is None else classes
        try:
            return self.model.predict(
                images,
                classes=cls,
                verbose=False,
                **params,
            )
        except Exception as exc:
            if is_cuda_oom_error(exc):
                raise CudaOutOfMemoryError(
                    f"YOLO predict failed due to CUDA OOM: {exc}"
                ) from exc
            raise

    def release(self) -> None:
        self.model = None


def yolo_results_to_dto_list(results: Any) -> list:
    """Convert Ultralytics result objects to MP DTO dict lists per image."""
    dto_results = []
    for res in results:
        items = []
        try:
            boxes = res.boxes
            if boxes is not None:
                coords, confs, cls_ids = _extract_box_arrays(boxes)
                for bbox, conf, cls_id in zip(coords, confs, cls_ids):
                    items.append(
                        {
                            "bbox_xyxy": [float(x) for x in bbox],
                            "confidence": float(conf),
                            "class_id": int(cls_id),
                        }
                    )
        except Exception:
            items = []
        dto_results.append(items)
    return dto_results


def _extract_box_arrays(boxes):
    try:
        xyxy = getattr(boxes, "xyxy", None)
        conf = getattr(boxes, "conf", None)
        cls_ids = getattr(boxes, "cls", None)
        if xyxy is not None and conf is not None and cls_ids is not None:
            try:
                if hasattr(xyxy, "cpu"):
                    xyxy = xyxy.cpu()
                if hasattr(conf, "cpu"):
                    conf = conf.cpu()
                if hasattr(cls_ids, "cpu"):
                    cls_ids = cls_ids.cpu()
            except Exception:
                pass
            coords = xyxy.tolist() if hasattr(xyxy, "tolist") else list(xyxy)
            confs = conf.tolist() if hasattr(conf, "tolist") else list(conf)
            cls = cls_ids.tolist() if hasattr(cls_ids, "tolist") else list(cls_ids)
            return coords or [], confs or [], cls or []
    except Exception:
        pass
    try:
        arr = boxes.cpu().numpy()
    except Exception:
        arr = boxes.numpy()
    coords = arr.xyxy.tolist() if arr.xyxy is not None else []
    confs = arr.conf.tolist() if arr.conf is not None else []
    cls = arr.cls.tolist() if arr.cls is not None else []
    return coords, confs, cls
