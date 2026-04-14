from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import shared_memory
from threading import Lock
from typing import Dict, Tuple

import numpy as np


@dataclass(frozen=True)
class FrameHandle:
    frame_id: int
    shm_name: str
    shape: Tuple[int, ...]
    dtype: str
    stride: Tuple[int, ...]
    timestamp: float


class SharedFrameTransport:
    """Simple shared-memory transport for frame descriptors."""

    def __init__(self):
        self._segments: Dict[str, shared_memory.SharedMemory] = {}
        self._lock = Lock()

    def alloc_frame(self, image: np.ndarray, frame_id: int, timestamp: float) -> FrameHandle:
        arr = np.ascontiguousarray(image)
        shm = shared_memory.SharedMemory(create=True, size=arr.nbytes)
        with self._lock:
            self._segments[shm.name] = shm
        view = np.ndarray(arr.shape, dtype=arr.dtype, buffer=shm.buf)
        view[:] = arr
        return FrameHandle(
            frame_id=frame_id,
            shm_name=shm.name,
            shape=arr.shape,
            dtype=str(arr.dtype),
            stride=arr.strides,
            timestamp=float(timestamp),
        )

    def get_frame_view(self, handle: FrameHandle) -> np.ndarray:
        shm = shared_memory.SharedMemory(name=handle.shm_name)
        try:
            view = np.ndarray(handle.shape, dtype=np.dtype(handle.dtype), buffer=shm.buf)
            return np.array(view, copy=True)
        finally:
            shm.close()

    def release_frame(self, handle: FrameHandle) -> None:
        with self._lock:
            shm = self._segments.pop(handle.shm_name, None)
        if shm is not None:
            try:
                shm.close()
            finally:
                shm.unlink()
            return
        shm = shared_memory.SharedMemory(name=handle.shm_name)
        try:
            shm.close()
        finally:
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
