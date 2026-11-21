"""Ultralytics RT-DETR runtime adapter."""

from __future__ import annotations

import logging

from .yolo_runtime import UltralyticsRuntime


class RtdetrRuntime(UltralyticsRuntime):
    """Run RT-DETR through the shared Ultralytics inference contract."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        super().__init__(self._load_rtdetr, "RT-DETR", logger)

    @staticmethod
    def _load_rtdetr(model_path: str):
        from ultralytics import RTDETR

        return RTDETR(model_path)
