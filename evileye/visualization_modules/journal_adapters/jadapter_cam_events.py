from ...core.base_class import EvilEyeBase

try:
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from abc import abstractmethod, ABC
from .jadapter_base import JournalAdapterBase


class JournalAdapterCamEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        # Return columns compatible with EventsJournal:
        # time_stamp, type, information, source_name, time_lost, preview_path, lost_preview_path, object_id, zone_id, event_id, source_id
        query = ('SELECT time_stamp, '
                 'CAST(\'CameraEvent\' AS text) AS type, '
                 '(\'Camera=\' || camera_full_address || \' \' || '
                 'CASE WHEN connection_status then \'reconnect\' ELSE \'disconnect\' END) AS information, '
                 'camera_full_address AS source_name, '
                 'NULL as time_lost, '
                 'NULL AS preview_path, NULL AS lost_preview_path, '
                 'NULL AS video_path, NULL AS video_path_lost, '
                 'NULL::integer AS object_id, NULL::integer AS zone_id, '
                 'event_id::integer AS event_id, '
                 'NULL::integer AS source_id FROM camera_events')
        return query
