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
    """FIFO pending jobs paired with MpControl input submissions.

    Invariant: dropping a job whose payload is still in ``input_queue`` must
    remove that payload in the same step. Releasing SHM / pending without a
    matching queue drop orphans handles for the worker and desynchronizes
    drain pairing (``pop_head`` vs result order).
    """

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
        # Queue full: drop oldest still-queued payload + its pending job, retry.
        # New job is already in pending but was not put — exclude it from pairing.
        with self._lock:
            submitted = max(0, len(self._pending) - 1)
        if self._evict_queued_head(submitted_jobs=submitted):
            try:
                self._mp_control.put_nowait(payload)
                return True
            except Exception:
                pass
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
        """Release all pending jobs. Caller should drain IPC queues first on restart."""
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

    def _queue_size(self) -> int | None:
        try:
            return int(self._input_queue.qsize())
        except Exception:
            return None

    def _try_drop_input_head(self) -> bool:
        try:
            self._input_queue.get_nowait()
            return True
        except Exception:
            return False

    def _pop_pending_at_locked(self, index: int) -> JobT | None:
        if index < 0 or index >= len(self._pending):
            return None
        if index == 0:
            return self._pending.popleft()
        self._pending.rotate(-index)
        job = self._pending.popleft()
        self._pending.rotate(index)
        return job

    def _evict_queued_head(self, *, submitted_jobs: int | None) -> bool:
        """Drop input_queue head and the pending job that owns that payload.

        ``submitted_jobs`` is the number of pending entries that were successfully
        put on the queue (excludes a just-appended job that failed put). When
        None, all current pending entries are treated as submitted.
        """
        qsize = self._queue_size()
        if not self._try_drop_input_head():
            return False
        with self._lock:
            depth = len(self._pending)
            if depth == 0:
                return True
            if submitted_jobs is None:
                submitted = depth
            else:
                submitted = max(0, min(int(submitted_jobs), depth))
            # qsize was measured before get_nowait; after drop the removed payload
            # was queue head among ``submitted`` jobs → pending index =
            # in_flight = submitted - qsize_before.
            if qsize is None:
                idx = 0
            else:
                idx = max(0, submitted - qsize)
                if idx >= depth:
                    idx = 0
            evicted = self._pop_pending_at_locked(idx)
            if evicted is not None:
                self._release_on_drop(evicted)
                self._diag_pending_evict += 1
        return True

    def _enforce_pending_cap_locked(self) -> None:
        # Called under self._lock before appending a new job.
        while self._pending_cap > 0 and len(self._pending) >= self._pending_cap:
            qsize = self._queue_size()
            # Must drop queue payload before releasing pending/SHM.
            try:
                self._input_queue.get_nowait()
            except Exception:
                # Oldest jobs are in-flight; soft-cap — stop rather than desync.
                break
            depth = len(self._pending)
            if qsize is None:
                idx = 0
            else:
                idx = max(0, depth - qsize)
                if idx >= depth:
                    idx = 0
            evicted = self._pop_pending_at_locked(idx)
            if evicted is not None:
                self._release_on_drop(evicted)
                self._diag_pending_evict += 1
