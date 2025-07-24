from abc import ABC
import numpy as np


class TrackEncoder(ABC):
    def inference(self, img: np.ndarray, dets: np.ndarray) -> np.ndarray:
        pass

