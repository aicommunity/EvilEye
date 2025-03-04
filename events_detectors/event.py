class Event:
    def __init__(self, timestamp, alarm_type, is_finished=False):
        self.event_id = None
        self.timestamp = timestamp
        self.alarm_type = alarm_type
        self.finished = is_finished
        self.long_term = False

    def __str__(self):
        return f'Id: {self.event_id}'

    def get_event_info(self):
        return str(self)

    def get_name(self):
        return self.__class__.__name__

    def set_id(self, global_id):
        self.event_id = global_id

    def is_long_term(self):
        return self.long_term

    def is_finished(self):
        return self.finished

    def get_time_finished(self):
        return self.timestamp
