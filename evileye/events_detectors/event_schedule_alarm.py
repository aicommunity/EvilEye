from .event import Event
from .event_zone import _resolve_event_image


class ScheduleAlarmEvent(Event):
    def __init__(self, timestamp, alarm_type, obj, is_finished=False):
        super().__init__(timestamp, alarm_type, is_finished)
        self.source_id = obj.source_id
        self.object_id = obj.object_id
        self.class_id = getattr(obj, "class_id", None)
        self.time_obj_detected = obj.time_detected
        self.time_lost = obj.time_lost
        self.long_term = True
        self.video_path = None
        self.video_path_lost = None
        # TD-PS-D8: schedule alarms used to carry no frames, so the journal
        # preview column was empty. Snapshot the object's last frame the same
        # way zone events do.
        if is_finished:
            self.img_detected = None
            self.img_lost = _resolve_event_image(obj)
        else:
            self.img_detected = _resolve_event_image(obj)
            self.img_lost = None

    def __str__(self):
        return (
            f"Id: {self.event_id}, Source: {self.source_id}, "
            f"Obj_id: {self.object_id}, Time: {self.time_obj_detected}"
        )

    def __eq__(self, other):
        return self.source_id == other.source_id and self.object_id == other.object_id

    def update_on_finished(self, finished_event):
        self.time_lost = finished_event.time_lost
        self.video_path_lost = getattr(finished_event, "video_path_lost", None)
        # Carry the lost-frame snapshot onto the long-lived event: adapters
        # update *this* object, not the finished copy.
        lost_image = getattr(finished_event, "img_lost", None)
        if lost_image is not None:
            self.img_lost = lost_image

    def get_time_finished(self):
        return self.time_lost


class FieldOfViewEvent(ScheduleAlarmEvent):
    """Deprecated alias for ScheduleAlarmEvent."""

    def get_name(self):
        return "FieldOfViewEvent"
