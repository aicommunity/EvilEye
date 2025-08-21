from .event import Event


class FieldOfViewEvent(Event):
    def __init__(self, timestamp, alarm_type, obj, is_finished=False):
        super().__init__(timestamp, alarm_type, is_finished)
        self.source_id = obj.source_id
        self.object_id = obj.object_id
        self.time_obj_detected = obj.time_detected
        self.time_lost = obj.time_lost
        self.long_term = True

    def __str__(self):
        return f'Id: {self.event_id}, Source: {self.source_id}, Obj_id: {self.object_id}, Time: {self.time_obj_detected}'

    def __eq__(self, other):
        return self.source_id == other.source_id and self.object_id == other.object_id

    def update_on_finished(self, finished_event):
        self.time_lost = finished_event.time_lost

    def get_time_finished(self):
        return self.time_lost
