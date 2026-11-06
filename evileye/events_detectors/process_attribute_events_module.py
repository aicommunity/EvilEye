"""Process-safe attribute event detector using bounded JPEG frame attachments."""

from __future__ import annotations

from types import SimpleNamespace

from evileye.core.event_time import obj_found_datetime, obj_lost_datetime
from evileye.events_detectors.event_attribute import AttributeEvent


class ProcessAttributeEventsModule:
    def __init__(self, config):
        self.config = dict(config or {})
        self.sources_expected = {}
        for source, event_map in (self.config.get("sources") or {}).items():
            try:
                source_id = int(source)
            except (TypeError, ValueError):
                continue
            self.sources_expected[source_id] = {
                str(event_name): set(attributes or ())
                for event_name, attributes in (event_map or {}).items()
            }

    @staticmethod
    def create_state(config, context):
        return {"active_events": set()}

    @staticmethod
    def _object(snapshot, update):
        frame_ref = snapshot.get("last_image_ref")
        event_frame = update.get_frame(frame_ref)
        last_image = event_frame
        track = SimpleNamespace(bounding_box=snapshot.get("bbox"))
        return SimpleNamespace(
            object_id=snapshot.get("object_id"),
            global_id=snapshot.get("global_id"),
            source_id=snapshot.get("source_id", update.source_id),
            class_id=snapshot.get("class_id"),
            frame_id=snapshot.get("frame_id"),
            time_stamp=snapshot.get("timestamp"),
            time_detected=snapshot.get("time_detected"),
            time_lost=snapshot.get("time_lost"),
            attributes=snapshot.get("attributes") or {},
            track=track,
            last_image=last_image,
        )

    def process_update(self, update, state):
        if update.kind != "object_snapshot":
            raise ValueError(
                f"AttributeEventsDetector does not accept update kind {update.kind!r}"
            )
        if update.source_id is None:
            raise ValueError("AttributeEventsDetector requires source_id")
        source_id = int(update.source_id)
        expected_map = self.sources_expected.get(source_id, {})
        if not expected_map:
            return []

        events = []
        for snapshot in update.payload.get("active", ()):
            obj = self._object(snapshot, update)
            current_attributes = {
                name
                for name, status in obj.attributes.items()
                if isinstance(status, dict) and status.get("state") == "exists"
            }
            for event_name, expected_attributes in expected_map.items():
                key = (source_id, obj.object_id, event_name)
                if current_attributes != expected_attributes or key in state["active_events"]:
                    continue
                events.append(
                    AttributeEvent(
                        obj_found_datetime(obj),
                        "AttributeEvent",
                        source_id,
                        obj.object_id,
                        event_name,
                        sorted(expected_attributes),
                        is_finished=False,
                        obj=obj,
                    )
                )
                state["active_events"].add(key)

        for snapshot in update.payload.get("lost", ()):
            obj = self._object(snapshot, update)
            for event_name, expected_attributes in expected_map.items():
                key = (source_id, obj.object_id, event_name)
                if key not in state["active_events"]:
                    continue
                events.append(
                    AttributeEvent(
                        obj_lost_datetime(obj),
                        "AttributeEvent",
                        source_id,
                        obj.object_id,
                        event_name,
                        sorted(expected_attributes),
                        is_finished=True,
                        obj=obj,
                    )
                )
                state["active_events"].remove(key)
        return events


def create_process_attribute_events_module(config):
    return ProcessAttributeEventsModule(config)
