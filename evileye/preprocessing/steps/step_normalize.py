from __future__ import annotations

import cv2
import numpy as np

from .step_abstract import StepAbstract


class Normalize(StepAbstract):
    """Нормализация изображения в указанный диапазон."""

    def __init__(self, next_step: StepAbstract | None = None, alpha: int = 0, beta: int = 255):
        super().__init__(next_step)
        self.alpha = alpha
        self.beta = beta

    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        return cv2.normalize(frame, None, alpha=self.alpha, beta=self.beta, norm_type=cv2.NORM_MINMAX)