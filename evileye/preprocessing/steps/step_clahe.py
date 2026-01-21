from __future__ import annotations

import cv2
import numpy as np

from .step_abstract import StepAbstract

"""
https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html
"""


class Clahe(StepAbstract):
    """Контрастная адаптивная гистограмма (CLAHE) для улучшения яркости."""

    def __init__(
        self,
        next_step: StepAbstract | None = None,
        clipLimit: float = 2.0,
        tileGridSize: tuple[int, int] = (8, 8),
    ):
        super().__init__(next_step)
        if clipLimit <= 0:
            raise ValueError("clipLimit must be positive")
        if len(tileGridSize) != 2 or tileGridSize[0] <= 0 or tileGridSize[1] <= 0:
            raise ValueError("tileGridSize must be a tuple of two positive integers")
        self.claheFilter = cv2.createCLAHE(clipLimit, tuple(tileGridSize))

    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        labImg = cv2.cvtColor(frame, cv2.COLOR_BGR2LAB)
        labPlanes = list(cv2.split(labImg))  # Convert to list for mutable access
        labPlanes[0] = self.claheFilter.apply(labPlanes[0])
        labImg = cv2.merge(labPlanes)
        return cv2.cvtColor(labImg, cv2.COLOR_LAB2BGR)