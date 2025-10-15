from .event import Event


class SystemEvent(Event):
    def __init__(self, timestamp, event_type: str):
        # event_type expected values: 'SystemStart' | 'SystemStop'
        super().__init__(timestamp, 'Info', True)
        self.event_type = event_type

    def __str__(self):
        return f'Id: {self.event_id}, Type: {self.event_type}, Time: {self.timestamp}'

    def get_name(self):
        # Name used to map to DB adapter in EventsProcessor
        return 'SystemEvent'


