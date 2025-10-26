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
        # time_stamp, type, event_details, time_lost, information, preview_path, lost_preview_path
        query = (
            'SELECT time_stamp, '
            "CAST('SystemEvent' AS text) AS type, "
            "CAST(NULL AS text) AS event_details, "
            'NULL as time_lost, '
            "(CASE WHEN event_type = 'SystemStart' THEN 'System started' ELSE 'System stopped' END) AS information, "
            'NULL AS preview_path, NULL AS lost_preview_path FROM system_events'
        )
        return query


