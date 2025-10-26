from .jadapter_base import JournalAdapterBase


class JournalAdapterZoneEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        query = ('SELECT time_entered AS time_stamp, '
                 'CAST(\'ZoneEvent\' AS text) AS type, '
                 'CAST(source_id AS text) AS event_details, '
                 'time_left AS time_lost, '
                 '(\'Intrusion detected in zone on source \' || source_id) AS information, '
                 'preview_path_entered AS preview_path, preview_path_left AS lost_preview_path FROM zone_events')
        return query
