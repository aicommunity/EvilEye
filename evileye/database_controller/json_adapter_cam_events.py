import os
import json
import datetime
from .db_adapter import DatabaseAdapterBase


class JsonAdapterCamEvents(DatabaseAdapterBase):
    """Persist camera connection events to JSON files."""

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
        self.event_name = 'CameraEvent'
        self.table_name = 'camera_events_json'

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
        file_path = os.path.join(day_dir, 'camera_events.json')

        records = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f) or []
            except Exception:
                records = []

        rec = {
            'event_id': event.event_id,
            'ts': event.timestamp.isoformat() if hasattr(event.timestamp, 'isoformat') else str(event.timestamp),
            'camera_full_address': getattr(event, 'camera_address', ''),
            'connection_status': getattr(event, 'con_status', False),
        }
        records.append(rec)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _update_impl(self, event):
        pass




