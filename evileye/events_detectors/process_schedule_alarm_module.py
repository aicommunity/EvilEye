"""Process-safe schedule alarm detector using serializable object snapshots."""

from __future__ import annotations

import time
from types import SimpleNamespace

from evileye.core.event_time import datetime_from_ts, obj_found_datetime, obj_lost_datetime
from evileye.events_detectors.event_schedule_alarm import ScheduleAlarmEvent
from evileye.events_detectors.schedule_alarm_logic import (
    effective_schedule_for_source,
    find_first_schedule_hit_in_history,
    matches_class,
    parse_detector_params,
)


class ProcessScheduleAlarmModule:
    def __init__(self, config):
        self.config = dict(config or {})
        self.schedule_config = parse_detector_params(self.config)

    def create_state(self, config, context):
        return {
            "active_obj_ids": {},
            "lost_obj_ids": {},
            "last_alarm_at": {},
        }

    @staticmethod
    def _object(snapshot):
        history = [
            SimpleNamespace(
                object_id=item.get("object_id"),
                global_id=item.get("global_id"),
                source_id=item.get("source_id"),
                class_id=item.get("class_id"),
                frame_id=item.get("frame_id"),
                time_stamp=datetime_from_ts(item.get("timestamp")),
                time_detected=datetime_from_ts(item.get("time_detected")),
                time_lost=datetime_from_ts(item.get("time_lost")),
            )
            for item in snapshot.get("history", ())
        ]
        return SimpleNamespace(
            object_id=snapshot.get("object_id"),
            global_id=snapshot.get("global_id"),
            source_id=snapshot.get("source_id"),
            class_id=snapshot.get("class_id"),
            frame_id=snapshot.get("frame_id"),
            time_stamp=datetime_from_ts(snapshot.get("timestamp")),
            time_detected=datetime_from_ts(snapshot.get("time_detected")),
            time_lost=datetime_from_ts(snapshot.get("time_lost")),
            history=history,
        )

    def _cooldown_allows(self, state, source_id):
        cooldown = self.schedule_config.camera_cooldown_sec
        if cooldown <= 0:
            return True
        last = state["last_alarm_at"].get(source_id)
        return last is None or last <= 0 or (time.time() - last) >= cooldown

    def process_update(self, update, state):
        if update.kind != "object_snapshot":
            raise ValueError(
                f"ScheduleAlarmEventsDetector does not accept update kind {update.kind!r}"
            )
        if update.source_id is None:
            raise ValueError("ScheduleAlarmEventsDetector requires source_id")
        source_id = int(update.source_id)
        schedule = effective_schedule_for_source(self.schedule_config, source_id)
        if not schedule.enabled:
            return []

        active_bucket = state["active_obj_ids"].setdefault(source_id, set())
        lost_bucket = state["lost_obj_ids"].setdefault(source_id, set())
        events = []

        for snapshot in update.payload.get("active", ()):
            obj = self._object(snapshot)
            if obj.object_id in active_bucket:
                continue
            if not matches_class(obj, schedule.class_ids):
                continue
            idx = find_first_schedule_hit_in_history(obj.history, schedule)
            if idx == -1 or not self._cooldown_allows(state, source_id):
                continue
            history_obj = obj.history[idx]
            active_bucket.add(obj.object_id)
            state["last_alarm_at"][source_id] = time.time()
            events.append(
                ScheduleAlarmEvent(obj_found_datetime(history_obj), "Alarm", history_obj)
            )

        current_lost_ids = set()
        for snapshot in update.payload.get("lost", ()):
            obj = self._object(snapshot)
            if obj.object_id in active_bucket:
                active_bucket.remove(obj.object_id)
                current_lost_ids.add(obj.object_id)
                events.append(
                    ScheduleAlarmEvent(obj_lost_datetime(obj), "Alarm", obj, is_finished=True)
                )
                continue
            if obj.object_id in lost_bucket:
                current_lost_ids.add(obj.object_id)
                continue
            if not matches_class(obj, schedule.class_ids):
                continue
            if find_first_schedule_hit_in_history(obj.history, schedule) == -1:
                continue
            current_lost_ids.add(obj.object_id)
            events.append(
                ScheduleAlarmEvent(obj_lost_datetime(obj), "Alarm", obj, is_finished=True)
            )

        lost_bucket.clear()
        lost_bucket.update(current_lost_ids)
        return events


def create_process_schedule_alarm_module(config):
    return ProcessScheduleAlarmModule(config)
