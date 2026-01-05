from ...core.base_class import EvilEyeBase

try:
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from abc import abstractmethod, ABC
from .jadapter_base import JournalAdapterBase


class JournalAdapterFieldOfViewEvents(JournalAdapterBase):
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
        query = ('SELECT fe.time_stamp, '
                 'CAST(\'FOVEvent\' AS text) AS type, '
                 '(\'Intrusion detected on source \' || fe.source_id) AS information, '
                 'COALESCE((SELECT DISTINCT o.source_name FROM objects o WHERE o.source_id = fe.source_id LIMIT 1), CAST(fe.source_id AS text)) AS source_name, '
                 'fe.time_lost, '
                 'fe.preview_path, fe.lost_preview_path FROM fov_events fe')
        return query
