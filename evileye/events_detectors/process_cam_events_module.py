"""Process-safe built-in camera connection event detector."""

from __future__ import annotations

from evileye.core.event_time import datetime_from_ts
from evileye.core.contracts import EventUpdate
from evileye.events_detectors.event_cameras import CameraEvent


class ProcessCamEventsModule:
    """Convert serialized source transition batches into CameraEvent values."""

    def __init__(self, config):
        self.config = dict(config or {})

    def process_update(self, update: EventUpdate, state):
        if update.kind != "source_status":
            raise ValueError(
                f"CamEventsDetector does not accept update kind {update.kind!r}"
            )
        events = []
        for key in ("disconnects", "reconnects"):
            for transition in update.payload.get(key, ()):
                timestamp = datetime_from_ts(transition.get("timestamp"))
                events.append(
                    CameraEvent(
                        str(transition["address"]),
                        bool(transition["is_connected"]),
                        timestamp,
                        "Warning",
                    )
                )
        return events


def create_process_cam_events_module(config):
    return ProcessCamEventsModule(config)
