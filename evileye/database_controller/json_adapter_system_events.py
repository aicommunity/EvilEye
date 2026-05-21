import os
import datetime
from .db_adapter import DatabaseAdapterBase
from .json_event_io import append_json_record


class JsonAdapterSystemEvents(DatabaseAdapterBase):
    """Persist system events (start/stop) to JSON files."""

    def __init__(self, db_controller=None):
        self.image_dir = None
        self.base_dir = None
        super().__init__(db_controller or self)

    def get_params(self):
        return {'image_dir': self.image_dir}

    def get_cameras_params(self):
        return {}

    def set_params_impl(self):
        cfg = self.params or {}
        self.image_dir = cfg.get('image_dir', 'EvilEyeData')
        self.base_dir = os.path.join(self.image_dir, 'Events')
        self.event_name = 'SystemEvent'
        self.table_name = 'system_events_json'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def start(self):
        self.run_flag = True

    def _process_queue_item(self, item):
        """JSON адаптер не использует очередь; метод требуется базовым классом."""
        return

    def stop(self):
        self.run_flag = False

    def _execute_query(self):
        pass

    def _insert_impl(self, event):
        date_folder = datetime.date.today().strftime('%Y-%m-%d')
        day_dir = os.path.join(self.base_dir, date_folder, 'Metadata')
        os.makedirs(day_dir, exist_ok=True)
        file_path = os.path.join(day_dir, 'system_events.json')

        rec = {
            'event_id': getattr(event, 'event_id', None),
            'ts': (event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)),
            'event_type': getattr(event, 'event_type', ''),
        }
        append_json_record(file_path, rec)

    def _update_impl(self, event):
        pass


