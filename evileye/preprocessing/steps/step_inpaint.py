from __future__ import annotations

import cv2
import numpy as np

from .step_abstract import StepAbstract

"""
https://docs.opencv.org/3.4/df/d3d/tutorial_py_inpainting.html
"""


class Inpaint(StepAbstract):
    """Удаление артефактов по маске через OpenCV inpaint."""

    def __init__(
        self,
        next_step: StepAbstract | None = None,
        thresholdMin: int = 100,
        thresholdMax: int = 255,
        inpaintRadius: float = 0.1,
    ):
        super().__init__(next_step)
        if thresholdMin < 0 or thresholdMax < 0 or thresholdMin > 255 or thresholdMax > 255:
            raise ValueError("thresholdMin/thresholdMax must be in range [0, 255]")
        if thresholdMin > thresholdMax:
            raise ValueError("thresholdMin cannot be greater than thresholdMax")
        if inpaintRadius <= 0:
            raise ValueError("inpaintRadius must be positive")
        self.thresholdMin = thresholdMin
        self.thresholdMax = thresholdMax
        self.inpaintRadius = inpaintRadius

    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        # Making mask
        grayImg = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        mask = cv2.threshold(grayImg, self.thresholdMin, self.thresholdMax, cv2.THRESH_BINARY)[1]

        # Inpainting
        return cv2.inpaint(frame, mask, self.inpaintRadius, cv2.INPAINT_TELEA)