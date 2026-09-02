"""Backward compatibility aliases for schedule alarm events."""

from __future__ import annotations

LEGACY_EVENT_ALIASES = {
    "FieldOfViewEvent": "ScheduleAlarmEvent",
    "FOVEvent": "ScheduleAlarmEvent",
}

LEGACY_JOURNAL_TYPES = {
    "fov_found": "schedule_alarm_found",
    "fov_lost": "schedule_alarm_lost",
}

LEGACY_JSON_FOUND = "fov_events_found.json"
LEGACY_JSON_LOST = "fov_events_lost.json"
NEW_JSON_FOUND = "schedule_alarm_events_found.json"
NEW_JSON_LOST = "schedule_alarm_events_lost.json"


def resolve_event_name(name: str) -> str:
    return LEGACY_EVENT_ALIASES.get(name, name)


def resolve_journal_type(name: str) -> str:
    return LEGACY_JOURNAL_TYPES.get(name, name)
