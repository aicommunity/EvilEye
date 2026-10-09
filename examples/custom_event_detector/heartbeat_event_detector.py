"""Minimal custom event detector registered via the legacy event registry.

The detector emits generic AlarmEvent records into the shared journal path.
Enable in config::

    "events_detectors": {
      "enabled": ["CamEventsDetector", "HeartbeatEventDetector"],
      "HeartbeatEventDetector": {"interval_sec": 30}
    }

Import this module before Controller starts (PYTHONPATH or site package).
"""

from __future__ import annotations

import time
from typing import Any, List

from evileye.events_detectors.event_registry import register_event_detector
from evileye.events_detectors.events_detector import EventsDetector
from evileye.events_detectors.alarm_event import AlarmEvent


@register_event_detector("HeartbeatEventDetector")
class HeartbeatEventDetector(EventsDetector):
    """Emits a generic alarm event on a fixed interval."""

    def __init__(self, objects_handler=None):
        super().__init__()
        self._objects_handler = objects_handler
        self.interval_sec = 30.0
        self._last_ts = 0.0

    def set_params_impl(self):
        if self.params:
            self.interval_sec = float(self.params.get("interval_sec", self.interval_sec))

    def get_params_impl(self):
        return {"interval_sec": self.interval_sec}

    def init_impl(self):
        self._last_ts = time.time()
        return True

    def process(self):
        while self.run_flag:
            try:
                item = self.queue_in.get(timeout=0.5)
            except Exception:
                item = None
            if item is None and not self.run_flag:
                break
            self.update()

    def update(self, *args: Any, **kwargs: Any) -> None:
        now = time.time()
        if now - self._last_ts < self.interval_sec:
            return
        self._last_ts = now
        event = AlarmEvent(
            "Heartbeat",
            severity="info",
            source_name="HeartbeatEventDetector",
            details={"timestamp": now},
        )
        try:
            self.queue_out.put_nowait(event)
        except Exception:
            self.logger.exception("HeartbeatEventDetector could not publish its alarm")
