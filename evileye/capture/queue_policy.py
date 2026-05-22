"""Shared drop-oldest policy for capture MP output queues and in-process deques."""

from __future__ import annotations

from collections import deque
from typing import Callable


def put_drop_oldest_deque(dq: deque, maxsize: int, item) -> bool:
    """DropOldestQueue semantics: return True if oldest was evicted."""
    dropped = len(dq) >= maxsize
    if dropped:
        dq.popleft()
    dq.append(item)
    return dropped


def put_drop_oldest(queue, item, *, on_drop: Callable[[object], None] | None = None) -> bool:
    """Put on a bounded queue; drop oldest when full. Returns True if put succeeded."""
    try:
        queue.put_nowait(item)
        return True
    except Exception:
        pass
    try:
        dropped = queue.get_nowait()
        if on_drop is not None:
            on_drop(dropped)
    except Exception:
        pass
    try:
        queue.put_nowait(item)
        return True
    except Exception:
        return False
