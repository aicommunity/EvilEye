"""Shared drop-oldest policy for capture MP output queues."""

from __future__ import annotations

from typing import Callable


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
