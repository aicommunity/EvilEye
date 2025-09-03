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
        query = ('SELECT CAST(\'Alarm\' AS text) AS type, time_stamp, time_lost, '
                 '(\'Intrusion detected on source \' || source_id) AS information, '
                 'preview_path, lost_preview_path FROM fov_events')
        return query
