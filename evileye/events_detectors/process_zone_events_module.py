"""Process isolated adapter for the built-in zone rule engine."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from evileye.core.event_time import datetime_from_ts
from evileye.core.contracts import EventUpdate
from evileye.events_detectors.zone_events_detector import ZoneEventsDetector


class _SnapshotObjectsHandler:
    def __init__(self):
        self.active = SimpleNamespace(objects=[])
        self.lost = SimpleNamespace(objects=[])

    def get(self, kind, source_id):
        return self.active if kind == "active" else self.lost


class ProcessZoneEventsModule:
    """Run the existing zone state machine against serialized object snapshots."""

    def __init__(self, config: dict[str, Any]):
        self.config = dict(config)
        self.handler = _SnapshotObjectsHandler()
        self.detector = None
        self.sticky_images: dict[tuple[int, int], Any] = {}

    def start(self):
        self.detector = ZoneEventsDetector(
            self.handler,
            listen_for_ui_events=False,
        )
        self.detector.set_params(**self.config)
        if self.detector.init() is False:
            raise RuntimeError("ZoneEventsDetector initialization returned false")

    @staticmethod
    def _track(bbox):
        return SimpleNamespace(bounding_box=bbox)

    @classmethod
    def _history_object(cls, snapshot):
        return SimpleNamespace(
            object_id=snapshot.get("object_id"),
            global_id=snapshot.get("global_id"),
            source_id=snapshot.get("source_id"),
            class_id=snapshot.get("class_id"),
            frame_id=snapshot.get("frame_id"),
            time_stamp=datetime_from_ts(snapshot.get("timestamp")),
            time_detected=datetime_from_ts(snapshot.get("time_detected")),
            time_lost=datetime_from_ts(snapshot.get("time_lost")),
            track=cls._track(snapshot.get("bbox")),
            last_image=None,
        )

    def _object(self, snapshot, update: EventUpdate):
        source_id = int(snapshot.get("source_id", update.source_id))
        object_id = int(snapshot["object_id"])
        history = [
            self._history_object(item)
            for item in snapshot.get("history", [])
            if item.get("bbox") is not None
        ]
        current = self._history_object(snapshot)
        current.source_id = source_id
        current.object_id = object_id
        current.history = history
        current.attributes = snapshot.get("attributes") or {}
        current.last_image = update.get_frame(snapshot.get("last_image_ref"))
        sticky = self.sticky_images.get((source_id, object_id))
        current._zone_event_sticky_image = sticky
        return current

    def process_command(self, command: str, kwargs: dict[str, Any]):
        if self.detector is None:
            raise RuntimeError("Zone event module has not started")
        method = getattr(self.detector, str(command), None)
        if not callable(method) or command not in {
            "add_zone",
            "delete_zone",
            "replace_zones_for_source",
            "apply_thresholds",
        }:
            raise ValueError(f"Unsupported zone event command: {command}")
        return method(**kwargs)

    def process_update(self, update: EventUpdate, state):
        if self.detector is None:
            raise RuntimeError("Zone event module has not started")
        if update.kind == "module_command":
            payload = update.payload
            return self.process_command(
                payload.get("command", ""),
                dict(payload.get("kwargs") or {}),
            )
        if update.kind != "object_snapshot" or update.source_id is None:
            raise ValueError(f"Unsupported zone event update kind: {update.kind!r}")

        source_id = int(update.source_id)
        active = [
            self._object(item, update)
            for item in update.payload.get("active", [])
        ]
        lost = [
            self._object(item, update)
            for item in update.payload.get("lost", [])
        ]
        self.handler.active = SimpleNamespace(objects=active)
        self.handler.lost = SimpleNamespace(objects=lost)
        events = self.detector._process_once({source_id})

        for obj in active:
            key = (source_id, obj.object_id)
            sticky = getattr(obj, "_zone_event_sticky_image", None)
            if sticky is None:
                self.sticky_images.pop(key, None)
            else:
                self.sticky_images[key] = sticky
        for obj in lost:
            self.sticky_images.pop((source_id, obj.object_id), None)
        return events

    def close(self):
        if self.detector is not None:
            self.detector.release()
            self.detector = None


def create_process_zone_events_module(config):
    return ProcessZoneEventsModule(config)
