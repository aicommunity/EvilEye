import core
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
from abc import abstractmethod, ABC
from visualization_modules.journal_adapters.jadapter_base import JournalAdapterBase


class JournalAdapterCamEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def init_impl(self):
        pass

    def select_query(self) -> str:
        query = ('SELECT CAST(\'Warning\' AS text) AS type, time_stamp, NULL as time_lost, '
                 '(\'Camera=\' || camera_full_address || \' \' || '
                 'CASE WHEN connection_status then \'reconnect\' ELSE \'disconnect\' END) AS information, '
                 'NULL AS preview_path, NULL AS lost_preview_path FROM camera_events')
        return query
