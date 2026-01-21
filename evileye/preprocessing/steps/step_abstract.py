from __future__ import annotations

from abc import abstractmethod
from typing import Optional, Protocol

import numpy as np


class IStep(Protocol):
    """Протокол для шагов препроцессинга."""

    def applySequence(self, frame: np.ndarray) -> np.ndarray:
        ...


class StepAbstract:
    """Базовый шаг препроцессинга c поддержкой последовательности шагов."""

    def __init__(self, next_step: Optional["StepAbstract"] = None):
        self.next_step = next_step

    def applySequence(self, frame: np.ndarray) -> np.ndarray:
        if frame is None or (isinstance(frame, np.ndarray) and frame.size == 0):
            raise ValueError("Empty frame passed to preprocessing step")

        current_step: Optional[StepAbstract] = self
        current_frame = frame
        while current_step is not None:
            current_frame = current_step._applyStep(current_frame)
            current_step = current_step.next_step
        return current_frame

    @abstractmethod
    def _applyStep(self, frame: np.ndarray) -> np.ndarray:
        """Выполнить конкретный шаг препроцессинга."""
        raise NotImplementedError