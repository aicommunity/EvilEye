import core
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
from abc import abstractmethod, ABC
from visualization_modules.journal_adapters.jadapter_base import JournalAdapterBase


class JournalAdapterCamEvents(JournalAdapterBase):
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
        query = ('SELECT CAST(\'Warning\' AS text) AS type, time_stamp, NULL as time_lost, '
                 '(\'Camera=\' || camera_full_address || \' \' || event_type) AS information, '
                 'NULL AS preview_path, NULL AS lost_preview_path FROM camera_events')
        # 'WHERE (time_stamp BETWEEN :start AND :finish) AND (source_id = :src_id) '
        # 'AND (camera_full_address = :address) ORDER BY time_stamp DESC')
        return query
