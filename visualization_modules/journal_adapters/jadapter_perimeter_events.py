import core
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
from abc import abstractmethod, ABC
from visualization_modules.journal_adapters.jadapter_base import JournalAdapterBase


class JournalAdapterPerimeterEvents(JournalAdapterBase):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def set_params_impl(self):
        self.table_name = self.params['table_name']

    def init_impl(self):
        pass

    def filter_by_camera_query(self, cam_id) -> QSqlQuery:
        pass

    def select_query(self) -> str:
        query = ('SELECT CAST(\'Alarm\' AS text) AS type, time_stamp, time_lost, '
                 '(\'Intrusion detected on source \' || source_id) AS information, '
                 'preview_path, lost_preview_path FROM perimeter_events')
        # 'WHERE (time_stamp BETWEEN :start AND :finish) AND (source_id = :src_id) '
        # 'AND (camera_full_address = :address) ORDER BY time_stamp DESC')
        return query
