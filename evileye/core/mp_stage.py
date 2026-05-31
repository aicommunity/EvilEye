"""Protocols for MP pipeline stages (pending stats, execution mode)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class MpStageProcessor(Protocol):
    execution_mode: str


@runtime_checkable
class MpPendingReporter(Protocol):
    def mp_pending_depth(self) -> int: ...

    def mp_diag_put_dropped(self) -> int: ...

    def mp_diag_pending_evict(self) -> int: ...
