"""Generic structured alarm event emitted by third-party rules/detectors."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping
from uuid import uuid4

from .event import Event


class AlarmEvent(Event):
    """Portable alarm envelope accepted by the shared event controller.

    ``alarm_id`` is the idempotency key used by persistence adapters. A plugin
    may pass its own stable key; otherwise a UUID is generated.
    """

    def __init__(
        self,
        alarm_type: str,
        *,
        severity: str = "warning",
        source_id: int | None = None,
        source_name: str | None = None,
        details: Mapping[str, Any] | None = None,
        timestamp: datetime | None = None,
        alarm_id: str | None = None,
    ) -> None:
        super().__init__(timestamp or datetime.now(), severity, is_finished=True)
        self.alarm_id = str(alarm_id or uuid4())
        self.alarm_type = str(alarm_type)
        self.severity = str(severity)
        self.source_id = source_id
        self.source_name = source_name
        self.details = dict(details or {})

    def get_name(self) -> str:
        return "AlarmEvent"

    def __str__(self) -> str:
        return (
            f"AlarmEvent(id={self.alarm_id}, type={self.alarm_type}, "
            f"severity={self.severity}, source={self.source_id})"
        )

