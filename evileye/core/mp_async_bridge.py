"""Shared FIFO pending queue + MP control put policy for feed/drain stages."""

from __future__ import annotations

import logging
import threading
from collections import deque
from typing import Callable, Generic, TypeVar

JobT = TypeVar("JobT")


class MpControlPutTarget:
    """Minimal MpControl surface used by MpAsyncBridge."""

    input_queue: object

    def put_nowait(self, data: object) -> None:
        ...


class MpAsyncBridge(Generic[JobT]):
    """FIFO pending jobs paired with MpControl input submissions."""

    def __init__(
        self,
        *,
        pending_cap: int,
        mp_control: MpControlPutTarget,
        release_on_drop: Callable[[JobT], None],
        logger: logging.Logger,
        input_queue: object | None = None,
    ) -> None:
        self._pending_cap = max(0, int(pending_cap))
        self._mp_control = mp_control
        self._input_queue = input_queue if input_queue is not None else mp_control.input_queue
        self._release_on_drop = release_on_drop
        self._logger = logger
        self._pending: deque[JobT] = deque()
        self._lock = threading.Lock()
        self._diag_put_dropped: int = 0
        self._diag_pending_evict: int = 0

    def enqueue(self, payload: object, job: JobT) -> bool:
        """Submit payload to MpControl; keep job in FIFO pending until drain pops it."""
        with self._lock:
            self._enforce_pending_cap_locked()
            self._pending.append(job)
        try:
            self._mp_control.put_nowait(payload)
            return True
        except Exception:
            pass
        try:
            self._input_queue.get_nowait()
        except Exception:
            pass
        with self._lock:
            if self._pending:
                evicted = self._pending.popleft()
                self._release_on_drop(evicted)
        try:
            self._mp_control.put_nowait(payload)
            return True
        except Exception:
            with self._lock:
                if self._pending and self._pending[-1] is job:
                    self._pending.pop()
            self._release_on_drop(job)
            self._diag_put_dropped += 1
            return False

    def pop_head(self) -> JobT | None:
        with self._lock:
            if not self._pending:
                return None
            return self._pending.popleft()

    def clear(self) -> None:
        with self._lock:
            while self._pending:
                job = self._pending.popleft()
                self._release_on_drop(job)

    def depth(self) -> int:
        with self._lock:
            return len(self._pending)

    def diag_put_dropped(self) -> int:
        return self._diag_put_dropped

    def diag_pending_evict(self) -> int:
        return self._diag_pending_evict

    def _enforce_pending_cap_locked(self) -> None:
        while self._pending_cap > 0 and len(self._pending) >= self._pending_cap:
            evicted = self._pending.popleft()
            self._release_on_drop(evicted)
            self._diag_pending_evict += 1
