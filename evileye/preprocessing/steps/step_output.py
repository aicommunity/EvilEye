from __future__ import annotations

import numpy as np

from .step_abstract import StepAbstract


class Output(StepAbstract):
    """Финальный шаг цепочки препроцессинга."""

    def __init__(self, next_step: StepAbstract | None = None):
        if next_step is not None:
            raise ValueError(f"Final sequence step must be None (got {next_step.__class__.__name__})")
        super().__init__(next_step)

    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        if frame is None:
            raise ValueError("Output step received None frame")
        return frame