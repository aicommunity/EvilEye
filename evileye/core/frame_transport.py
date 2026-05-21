from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import shared_memory
from multiprocessing import resource_tracker
from threading import Lock
from typing import Any, Dict, List, Optional, Tuple

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

    @staticmethod
    def _detach_from_resource_tracker(shm: shared_memory.SharedMemory) -> None:
        """
        Detach an attached (non-owner) segment from resource_tracker.
        Prevents child processes from trying to unlink segments they do not own.
        """
        try:
            raw_name = getattr(shm, "_name", None) or shm.name
            resource_tracker.unregister(raw_name, "shared_memory")
        except Exception:
            pass

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
        self._detach_from_resource_tracker(shm)
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
        # Foreign segment (created in another process): only close local handle.
        # Unlink is responsibility of the owner process to avoid cross-process
        # double-unlink warnings from multiprocessing resource_tracker.
        shm = shared_memory.SharedMemory(name=handle.shm_name)
        try:
            shm.close()
        except FileNotFoundError:
            pass


def materialize_payload_item(
    item: Any,
    transport: Optional[SharedFrameTransport] = None,
) -> Any:
    """Resolve FrameHandle to ndarray; pass through other items."""
    if not isinstance(item, FrameHandle):
        return item
    tr = transport or SharedFrameTransport()
    try:
        return tr.get_frame_view(item)
    except Exception:
        return None


def materialize_payload_list(
    data: List[Any],
    transport: Optional[SharedFrameTransport] = None,
) -> List[Any]:
    """Materialize a list of queue payloads that may contain FrameHandle entries."""
    return [materialize_payload_item(x, transport) for x in data]
