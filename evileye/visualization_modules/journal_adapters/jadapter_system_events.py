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
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path, object_id, zone_id, event_id, source_id
        query = (
            'SELECT time_stamp, '
            "CAST('SystemEvent' AS text) AS type, "
            "(CASE WHEN event_type = 'SystemStart' THEN 'System started' ELSE 'System stopped' END) AS information, "
            "'System' AS source_name, "
            'NULL as time_lost, '
            'NULL AS preview_path, NULL AS lost_preview_path, '
            'NULL AS video_path, NULL AS video_path_lost, '
            'NULL::integer AS object_id, NULL::integer AS zone_id, '
            'event_id::integer AS event_id, '
            'NULL::integer AS source_id FROM system_events'
        )
        return query


