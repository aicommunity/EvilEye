from __future__ import annotations

import os
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


def _pool_max_free_default() -> int:
    try:
        return max(0, int(os.getenv("EVILEYE_SHM_POOL_MAX_FREE", "16")))
    except ValueError:
        return 16


class SharedFrameTransport:
    """Simple shared-memory transport for frame descriptors.

    With ``pool_segments=True`` released segments are kept mapped and reused
    for later ``alloc_frame`` calls instead of being unlinked and recreated
    per frame (TD-PS-D2): the per-frame ``SharedMemory(create=True)`` syscall
    pair and the two extra copies of allocator churn disappear; only the
    unavoidable pixel copy into the segment remains. Reuse is safe because the
    caller releases a handle only after the consumer is done with the segment
    (request completion / worker envelope received).
    """

    def __init__(self, pool_segments: bool = False, pool_max_free: Optional[int] = None):
        self._segments: Dict[str, shared_memory.SharedMemory] = {}
        self._lock = Lock()
        self._pool_enabled = bool(pool_segments)
        self._pool_max_free = (
            _pool_max_free_default() if pool_max_free is None else max(0, int(pool_max_free))
        )
        # Idle segments available for reuse, keyed by (shape, dtype).
        self._free_segments: Dict[Tuple[Tuple[int, ...], str], List[shared_memory.SharedMemory]] = {}

    def alloc_frame(self, image: np.ndarray, frame_id: int, timestamp: float) -> FrameHandle:
        arr = np.ascontiguousarray(image)
        shm = None
        if self._pool_enabled:
            key = (arr.shape, str(arr.dtype))
            with self._lock:
                free_list = self._free_segments.get(key)
                while shm is None and free_list:
                    candidate = free_list.pop()
                    if candidate.size < arr.nbytes:
                        # Stale/small segment (e.g. resolution change): drop it.
                        self._close_quietly(candidate)
                        continue
                    shm = candidate
                if shm is not None:
                    # Segment is active again until release_frame().
                    self._segments[shm.name] = shm
        if shm is None:
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

    @staticmethod
    def _close_quietly(shm: shared_memory.SharedMemory) -> None:
        try:
            shm.close()
        except Exception:
            pass
        try:
            shm.unlink()
        except Exception:
            pass

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
            if shm is not None and self._pool_enabled:
                key = (handle.shape, handle.dtype)
                free_list = self._free_segments.setdefault(key, [])
                if len(free_list) < self._pool_max_free:
                    free_list.append(shm)
                    return
        if shm is not None:
            self._close_quietly(shm)
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
            owned = list(self._segments.values())
            free_lists = [seg for lst in self._free_segments.values() for seg in lst]
            self._segments.clear()
            self._free_segments.clear()
        for shm in owned:
            self._close_quietly(shm)
        for shm in free_lists:
            self._close_quietly(shm)


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
