from .event import Event
import copy


class ZoneEvent(Event):
    def __init__(self, timestamp, alarm_type, obj, zone, is_finished=False):
        super().__init__(timestamp, alarm_type, is_finished)
        self.source_id = obj.source_id
        self.zone = zone
        self.object_id = obj.object_id
        if not is_finished:
            self.img_entered = copy.deepcopy(obj.last_image)
            self.img_left = None
            self.box_entered = obj.track.bounding_box
            self.box_left = None
            self.time_entered = obj.time_stamp
            self.time_left = None
        else:
            self.img_entered = None
            self.img_left = copy.deepcopy(obj.last_image)
            self.box_entered = None
            self.box_left = obj.track.bounding_box
            self.time_entered = None
            self.time_left = obj.time_stamp

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

    def get_time_finished(self):
        return self.time_left
