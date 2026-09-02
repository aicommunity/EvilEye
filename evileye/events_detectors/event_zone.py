from .event import Event
import copy
from evileye.core.event_time import datetime_from_ts


def _copy_frame_image(frame):
    if frame is None:
        return None
    if not hasattr(frame, "image") or frame.image is None:
        return frame
    copied = copy.copy(frame)
    copied.image = frame.image.copy()
    return copied


def _resolve_event_image(obj, hist_obj=None):
    """Pick a frame snapshot for zone event metadata (enter/exit)."""
    for candidate in (obj, hist_obj):
        if candidate is None:
            continue
        last_image = getattr(candidate, "last_image", None)
        if last_image is not None and getattr(last_image, "image", None) is not None:
            return _copy_frame_image(last_image)
    history = getattr(obj, "history", None) or []
    for hist in reversed(history):
        hist_image = getattr(hist, "last_image", None)
        if hist_image is not None and getattr(hist_image, "image", None) is not None:
            return _copy_frame_image(hist_image)
    return None


class ZoneEvent(Event):
    def __init__(self, timestamp, alarm_type, obj, zone, is_finished=False, hist_obj=None):
        ts = datetime_from_ts(timestamp) or datetime_from_ts(getattr(obj, "time_stamp", None))
        super().__init__(ts or timestamp, alarm_type, is_finished)
        self.source_id = obj.source_id
        self.zone = zone
        self.object_id = obj.object_id
        if not is_finished:
            self.img_entered = _resolve_event_image(obj)
            self.img_left = None
            self.box_entered = obj.track.bounding_box
            self.box_left = None
            self.time_entered = ts or obj.time_stamp
            self.time_left = None
            self.video_path_entered = None
            self.video_path_left = None
        else:
            self.img_entered = None
            self.img_left = _resolve_event_image(obj, hist_obj=hist_obj)
            self.box_entered = None
            self.box_left = obj.track.bounding_box
            self.time_entered = None
            self.time_left = ts or obj.time_stamp
            self.video_path_entered = None
            self.video_path_left = None

        self.long_term = True

    def __str__(self):
        if self.finished:
            return f'Id: {self.event_id}, Source: {self.source_id}, Obj_id: {self.object_id}, Time: {self.time_left}'
        return f'Id: {self.event_id}, Source: {self.source_id}, Obj_id: {self.object_id}, Time: {self.time_entered}'

    def __eq__(self, other):
        return (self.source_id == other.source_id and self.object_id == other.object_id and
                self.zone == other.zone)

    def update_on_finished(self, finished_event):
        self.time_left = finished_event.time_left
        self.img_left = finished_event.img_left
        self.box_left = finished_event.box_left
        self.video_path_left = getattr(finished_event, 'video_path_left', None)

    def get_time_finished(self):
        return self.time_left
