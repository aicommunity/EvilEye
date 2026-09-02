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
        table = self.table_name or "schedule_alarm_events"
        return (
            f'SELECT fe.time_stamp, '
            f"CAST('ScheduleAlarmEvent' AS text) AS type, "
            f"('Schedule alarm on source ' || fe.source_id) AS information, "
            f'COALESCE(o.source_name, CAST(fe.source_id AS text)) AS source_name, '
            f'fe.time_lost, '
            f'fe.preview_path, fe.lost_preview_path, '
            f'fe.video_path, fe.video_path_lost, '
            f'fe.object_id::integer AS object_id, NULL::integer AS zone_id, '
            f'fe.event_id::integer AS event_id, '
            f'fe.source_id::integer AS source_id '
            f'FROM {table} fe '
            f'LEFT JOIN (SELECT source_id, MAX(source_name) AS source_name FROM objects GROUP BY source_id) o '
            f'ON o.source_id = fe.source_id'
        )
