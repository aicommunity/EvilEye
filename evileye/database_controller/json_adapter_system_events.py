import os
import json
import datetime
from .db_adapter import DatabaseAdapterBase


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
        self.base_dir = os.path.join(self.image_dir, 'images')
        self.event_name = 'SystemEvent'
        self.table_name = 'system_events_json'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def start(self):
        self.run_flag = True

    def stop(self):
        self.run_flag = False

    def _execute_query(self):
        pass

    def _insert_impl(self, event):
        date_folder = datetime.date.today().strftime('%Y_%m_%d')
        day_dir = os.path.join(self.base_dir, date_folder)
        os.makedirs(day_dir, exist_ok=True)
        file_path = os.path.join(day_dir, 'system_events.json')

        records = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f) or []
            except Exception:
                records = []

        rec = {
            'event_id': getattr(event, 'event_id', None),
            'ts': (event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp)),
            'event_type': getattr(event, 'event_type', ''),
        }
        records.append(rec)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _update_impl(self, event):
        pass


