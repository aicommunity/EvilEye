"""
Queue utilities for frame storage with optimized performance.

Provides a drop-oldest queue implementation using deque for better performance
while maintaining the intentional small size (2) to avoid stale frames.
"""

from collections import deque
from queue import Empty
from threading import Lock
from typing import Optional, Any


class DropOldestQueue:
    """Thread-safe queue with drop-oldest strategy when full.

    Returns flag from `put` indicating whether the oldest element was dropped.
    """

    def __init__(self, maxsize: int = 2):
        self.maxsize = maxsize
        self._deque: deque = deque(maxlen=maxsize)
        self._lock = Lock()

    def put(self, item: Any, block: bool = False, timeout: Optional[float] = None) -> bool:
        """Put item; drop oldest when full.

        Returns:
            True if an item had to be dropped to insert the new one.
        """
        with self._lock:
            dropped = len(self._deque) >= self.maxsize
            if dropped:
                # Manually drop to know that we did it
                self._deque.popleft()
            self._deque.append(item)
            return dropped

    def get(self, block: bool = False, timeout: Optional[float] = None) -> Any:
        with self._lock:
            if not self._deque:
                raise Empty
            return self._deque.popleft()

    def get_nowait(self) -> Any:
        return self.get(block=False)

    def empty(self) -> bool:
        with self._lock:
            return len(self._deque) == 0

    def full(self) -> bool:
        with self._lock:
            return len(self._deque) >= self.maxsize

    def qsize(self) -> int:
        with self._lock:
            return len(self._deque)

    def clear(self) -> None:
        with self._lock:
            self._deque.clear()

