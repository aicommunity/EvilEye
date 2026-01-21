from __future__ import annotations

import numpy as np

from .step_abstract import StepAbstract


class Input(StepAbstract):
    """Начальный шаг цепочки препроцессинга."""

    def __init__(self, next_step: StepAbstract | None = None):
        super().__init__(next_step)

    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        return frame