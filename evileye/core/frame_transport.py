from __future__ import annotations

from dataclasses import dataclass
from multiprocessing import shared_memory
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
            try:
                shm.close()
            except Exception:
                pass

    def relinquish_frame(self, handle: FrameHandle) -> None:
        """Mark a frame as transferred while keeping the creator mapping open.

        Windows removes a named shared-memory object after its last handle closes,
        even if a consumer has not opened the name yet. Keep the creator handle
        pinned until the consumer acknowledges the transfer; then call
        ``release_frame`` (or ``release_all_owned``). The consumer unlinks the name.
        """
        # Keep the SharedMemory object in _segments as a cross-platform pin.
        return

    def consume_frame(self, handle: FrameHandle) -> Optional[np.ndarray]:
        """Copy pixels from a foreign handle and unlink the segment (IPC consumer).

        Returns ``None`` when the SHM segment is missing or empty so callers can
        drop the frame instead of feeding a zero-size array into OpenCV/YOLO.
        """
        try:
            shm = shared_memory.SharedMemory(name=handle.shm_name)
        except FileNotFoundError:
            return None
        try:
            view = np.ndarray(
                handle.shape, dtype=np.dtype(handle.dtype), buffer=shm.buf
            )
            image = np.array(view, copy=True)
        finally:
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
            try:
                shm.close()
            except Exception:
                pass
        if image is None or getattr(image, "size", 0) == 0:
            return None
        return image

    def release_frame(self, handle: FrameHandle) -> None:
        with self._lock:
            shm = self._segments.pop(handle.shm_name, None)
        if shm is not None:
            try:
                shm.close()
            except Exception:
                pass
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
            return
        try:
            shm = shared_memory.SharedMemory(name=handle.shm_name)
        except FileNotFoundError:
            return
        try:
            try:
                shm.unlink()
            except FileNotFoundError:
                pass
        finally:
            try:
                shm.close()
            except Exception:
                pass

    def release_all_owned(self) -> None:
        """Close and unlink all segments owned by this transport instance."""
        with self._lock:
            names = list(self._segments.keys())
        for name in names:
            self.release_frame(
                FrameHandle(
                    frame_id=0,
                    shm_name=name,
                    shape=(),
                    dtype="uint8",
                    stride=(),
                    timestamp=0.0,
                )
            )


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
