from ...core.base_class import EvilEyeBase

try:
    from PyQt6.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery

    pyqt_version = 6
except ImportError:
    from PyQt5.QtSql import QSqlQueryModel, QSqlDatabase, QSqlQuery

    pyqt_version = 5

from abc import abstractmethod, ABC


# Базовый класс журнального адаптера, для того чтобы формировать SELECT запросы к соответствующим таблицам в БД
class JournalAdapterBase(EvilEyeBase, ABC):
    # TD-AUD-SQL-ID: select_query() interpolates table_name into raw SQL, so
    # it must come from a fixed set of event tables - never free-form config.
    KNOWN_EVENT_TABLES = frozenset({
        "zone_events", "attribute_events", "cam_events", "camera_events",
        "schedule_alarm_events", "fov_events", "alarm_events",
        "system_events", "objects",
    })

    def __init__(self):
        super().__init__()
        self.table_name = None
        self.event_name = None

    def set_params_impl(self):
        table = str(self.params.get('table_name') or '').strip()
        if table and table not in self.KNOWN_EVENT_TABLES:
            raise ValueError(
                f"table_name {table!r} is not a known event table "
                f"(allowed: {', '.join(sorted(self.KNOWN_EVENT_TABLES))})"
            )
        self.table_name = table or None

    def get_params_impl(self):
        params = dict()
        params['table_name'] = self.table_name
        return params

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
