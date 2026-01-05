from .jadapter_base import JournalAdapterBase


class JournalAdapterSystemEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        # Columns order must match union schema in EventsJournal
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path
        query = (
            'SELECT time_stamp, '
            "CAST('SystemEvent' AS text) AS type, "
            "(CASE WHEN event_type = 'SystemStart' THEN 'System started' ELSE 'System stopped' END) AS information, "
            "'System' AS source_name, "
            'NULL as time_lost, '
            'NULL AS preview_path, NULL AS lost_preview_path FROM system_events'
        )
        return query


