import core

try:
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 6
except ImportError:
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery
    pyqt_version = 5

from abc import abstractmethod, ABC


# Базовый класс журнального адаптера, для того чтобы формировать SELECT запросы к соответствующим таблицам в БД
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
