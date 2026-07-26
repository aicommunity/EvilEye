"""Capture queue_policy and DropOldestQueue alignment (MEM-5 partial)."""

import queue
import threading

from evileye.capture.queue_policy import put_drop_oldest, put_drop_oldest_deque
from evileye.capture.queue_utils import DropOldestQueue


def test_put_drop_oldest_deque():
    from collections import deque

    dq = deque(maxlen=3)
    dq.append(1)
    dq.append(2)
    assert put_drop_oldest_deque(dq, 2, 3) is True
    assert list(dq) == [2, 3]


def test_put_drop_oldest_mp_queue():
    dropped = []

    def on_drop(item):
        dropped.append(item)

    q = queue.Queue(maxsize=1)
    q.put("a")
    assert put_drop_oldest(q, "b", on_drop=on_drop) is True
    assert dropped == ["a"]
    assert q.get_nowait() == "b"


def test_drop_oldest_queue_matches_policy():
    q = DropOldestQueue(maxsize=2)
    assert q.put(1) is False
    assert q.put(2) is False
    assert q.put(3) is True
    assert q.get_nowait() == 2
    assert q.get_nowait() == 3
