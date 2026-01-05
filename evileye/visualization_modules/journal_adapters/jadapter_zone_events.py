from .jadapter_base import JournalAdapterBase


class JournalAdapterZoneEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        # Return columns compatible with EventsJournal:
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path
        # Get source_name from objects table using subquery
        query = ('SELECT ze.time_entered AS time_stamp, '
                 'CAST(\'ZoneEvent\' AS text) AS type, '
                 '(\'Intrusion detected in zone on source \' || ze.source_id) AS information, '
                 'COALESCE((SELECT DISTINCT o.source_name FROM objects o WHERE o.source_id = ze.source_id LIMIT 1), CAST(ze.source_id AS text)) AS source_name, '
                 'ze.time_left AS time_lost, '
                 'ze.preview_path_entered AS preview_path, ze.preview_path_left AS lost_preview_path FROM zone_events ze')
        return query
