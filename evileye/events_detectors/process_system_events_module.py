"""Process-safe built-in SystemEventsDetector implementation."""

from __future__ import annotations

from datetime import datetime

from evileye.core.event_time import datetime_from_ts
from evileye.core.contracts import EventUpdate
from evileye.events_detectors.event_system import SystemEvent


class ProcessSystemEventsModule:
    """Turn explicit controller commands into the established SystemEvent type."""

    def __init__(self, config):
        self.config = dict(config or {})

    def process_update(self, update: EventUpdate, state):
        if update.kind != "system_message":
            raise ValueError(
                f"SystemEventsDetector does not accept update kind {update.kind!r}"
            )
        event_type = str(update.payload.get("event_type") or "").strip()
        if not event_type:
            raise ValueError("system event type must not be empty")
        timestamp = datetime_from_ts(update.timestamp) or datetime.now()
        return SystemEvent(
            timestamp,
            event_type,
            str(update.payload.get("message") or ""),
        )


def create_process_system_events_module(config):
    return ProcessSystemEventsModule(config)
