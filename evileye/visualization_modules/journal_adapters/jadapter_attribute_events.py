from .jadapter_base import JournalAdapterBase


class JournalAdapterAttributeEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        # Return columns compatible with EventsJournal:
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path, object_id, zone_id, event_id
        # Get source_name from objects table using LEFT JOIN (much faster than correlated subquery per row)
        query = (
            "SELECT ae.time_stamp, "
            "CAST('AttributeEvent' AS text) AS type, "
            "('Attributes event ' || ae.event_name || ' on source ' || ae.source_id || ' obj=' || ae.object_id || ' class=' || ae.class_id || ' attrs=' || ae.attrs) AS information, "
            "COALESCE(o.source_name, CAST(ae.source_id AS text)) AS source_name, "
            "ae.time_finished AS time_lost, "
            "ae.preview_path_found AS preview_path, "
            "ae.preview_path_finished AS lost_preview_path, "
            "ae.video_path_found AS video_path, "
            "ae.video_path_finished AS video_path_lost, "
            "ae.object_id::integer AS object_id, NULL::integer AS zone_id, "
            "ae.event_id::integer AS event_id, "
            "ae.source_id::integer AS source_id "
            "FROM attribute_events ae "
            "LEFT JOIN (SELECT source_id, MAX(source_name) AS source_name FROM objects GROUP BY source_id) o ON o.source_id = ae.source_id"
        )
        return query
