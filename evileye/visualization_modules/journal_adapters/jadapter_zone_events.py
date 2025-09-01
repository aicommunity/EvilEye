from .jadapter_base import JournalAdapterBase


class JournalAdapterZoneEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        query = ('SELECT CAST(\'Alarm\' AS text) AS type, time_entered, time_left, '
                 '(\'Intrusion detected in zone on source \' || source_id) AS information, '
                 'preview_path_entered, preview_path_left FROM zone_events')
        return query
