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
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path, object_id, zone_id, event_id
        # Note: zone_id doesn't exist in zone_events table, so we use NULL
        # Get source_name from objects table using LEFT JOIN (much faster than correlated subquery per row)
        query = ('SELECT ze.time_entered AS time_stamp, '
                 'CAST(\'ZoneEvent\' AS text) AS type, '
                 '(\'Intrusion detected in zone on source \' || ze.source_id) AS information, '
                 'COALESCE(o.source_name, CAST(ze.source_id AS text)) AS source_name, '
                 'ze.time_left AS time_lost, '
                 'ze.preview_path_entered AS preview_path, ze.preview_path_left AS lost_preview_path, '
                 'ze.video_path_entered AS video_path, ze.video_path_left AS video_path_lost, '
                 'ze.object_id::integer AS object_id, NULL::integer AS zone_id, '
                 'ze.event_id::integer AS event_id, '
                 'ze.source_id::integer AS source_id '
                 'FROM zone_events ze '
                 'LEFT JOIN (SELECT source_id, MAX(source_name) AS source_name FROM objects GROUP BY source_id) o ON o.source_id = ze.source_id')
        return query
