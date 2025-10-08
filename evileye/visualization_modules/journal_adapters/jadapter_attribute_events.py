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
        # time, type, event_details, time_lost, information, preview_path, lost_preview_path
        query = (
            "SELECT time_stamp, "
            "CAST('AttributeEvent' AS text) AS type, "
            "event_name AS event_details, "
            "time_finished, "
            "('Attributes event ' || event_name || ' on source ' || source_id || ' obj=' || object_id || ' class=' || class_id || ' attrs=' || attrs) AS information, "
            "preview_path_found AS preview_path, "
            "preview_path_finished AS lost_preview_path "
            "FROM attribute_events"
        )
        return query
