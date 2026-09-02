from .event_schedule_alarm import FieldOfViewEvent, ScheduleAlarmEvent
from .schedule_alarm_events_detector import ScheduleAlarmEventsDetector

FieldOfViewEventsDetector = ScheduleAlarmEventsDetector

__all__ = [
    "FieldOfViewEvent",
    "FieldOfViewEventsDetector",
    "ScheduleAlarmEvent",
    "ScheduleAlarmEventsDetector",
]
