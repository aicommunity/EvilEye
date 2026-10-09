from .jadapter_base import JournalAdapterBase


class JournalAdapterAlarmEvents(JournalAdapterBase):
    """Expose generic alarm records through the unified SQL journal query."""

    def __init__(self):
        super().__init__()
        self.table_name = "alarm_events"
        self.event_name = "AlarmEvent"

    def init_impl(self):
        return None

    def select_query(self) -> str:
        return (
            "SELECT time_stamp, CAST('AlarmEvent' AS text) AS type, "
            "(COALESCE(alarm_type, 'Alarm') || ' [' || COALESCE(severity, 'warning') || '] ' "
            "|| COALESCE(details::text, '{}')) AS information, "
            "COALESCE(source_name, source_id::text, '') AS source_name, "
            "NULL AS time_lost, NULL AS preview_path, NULL AS lost_preview_path, "
            "NULL AS video_path, NULL AS video_path_lost, "
            "NULL::integer AS object_id, NULL::integer AS zone_id, "
            "event_id::integer AS event_id, source_id::integer AS source_id "
            f"FROM {self.table_name}"
        )

