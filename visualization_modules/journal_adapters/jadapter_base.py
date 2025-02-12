import core
from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
from abc import abstractmethod, ABC


class JournalAdapterBase(core.EvilEyeBase, ABC):
    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def set_params_impl(self):
        self.table_name = self.params['table_name']

    def init_impl(self):
        pass

    def get_event_name(self):
        return self.event_name

    def get_table_name(self):
        return self.table_name

    def default(self):
        pass

    def reset_impl(self):
        pass

    def release_impl(self):
        pass

    @abstractmethod
    def select_query(self) -> str:
        pass

    @abstractmethod
    def filter_by_camera_query(self, cam_id) -> QSqlQuery:
        pass
