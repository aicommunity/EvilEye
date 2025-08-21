from .event import Event


class CameraEvent(Event):
    def __init__(self, address, is_connected, timestamp, alarm_type, is_finished=True):
        super().__init__(timestamp, alarm_type, is_finished)
        self.camera_address = address
        self.long_term = False
        self.con_status = is_connected

    def __str__(self):
        return f'Id: {self.event_id}, Source: {self.camera_address}'

    def __eq__(self, other):
        return self.camera_address == other.camera_address and self.timestamp == self.timestamp

    def is_connected(self):
        return self.con_status
