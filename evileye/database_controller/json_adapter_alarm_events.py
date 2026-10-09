"""Generic JSON persistence for plugin-generated alarm events."""

from __future__ import annotations

import datetime
import json
import os
import threading

from .db_adapter import DatabaseAdapterBase


_WRITE_LOCK = threading.RLock()


class JsonAdapterAlarmEvents(DatabaseAdapterBase):
    def __init__(self, db_controller=None):
        self.image_dir = "EvilEyeData"
        self.base_dir = None
        super().__init__(db_controller or self)

    def get_params(self):
        return {"image_dir": self.image_dir}

    def get_cameras_params(self):
        return {}

    def set_params_impl(self):
        cfg = self.params or {}
        self.image_dir = cfg.get("image_dir", "EvilEyeData")
        self.base_dir = os.path.join(self.image_dir, "Events")
        self.event_name = "AlarmEvent"
        self.table_name = "alarm_events_json"

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def start(self):
        self.run_flag = True

    def stop(self):
        self.run_flag = False

    def _process_queue_item(self, item):
        return None

    def _execute_query(self):
        return None

    def _insert_impl(self, event):
        timestamp = getattr(event, "timestamp", datetime.datetime.now())
        date_folder = timestamp.strftime("%Y-%m-%d")
        day_dir = os.path.join(self.base_dir, date_folder, "Metadata")
        os.makedirs(day_dir, exist_ok=True)
        file_path = os.path.join(day_dir, "alarm_events.json")
        record = {
            "event_id": getattr(event, "event_id", None),
            "alarm_id": getattr(event, "alarm_id", None),
            "ts": timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp),
            "event_type": "alarm",
            "alarm_type": getattr(event, "alarm_type", "Alarm"),
            "severity": getattr(event, "severity", "warning"),
            "source_id": getattr(event, "source_id", None),
            "source_name": getattr(event, "source_name", None),
            "details": getattr(event, "details", {}),
        }
        # The JSON adapter is a synchronous durability boundary. Repeated
        # delivery is safe because alarm_id is stable across retries.
        with _WRITE_LOCK:
            if os.path.isfile(file_path):
                # Never replace an unreadable alarm journal with an empty list:
                # the caller retries and reports a degraded event path instead.
                with open(file_path, encoding="utf-8") as stream:
                    existing = json.load(stream)
                if not isinstance(existing, list):
                    raise ValueError(f"Alarm journal must contain a JSON list: {file_path}")
            else:
                existing = []
            alarm_id = record.get("alarm_id")
            if alarm_id and any(item.get("alarm_id") == alarm_id for item in existing if isinstance(item, dict)):
                return
            existing.append(record)
            temp_path = f"{file_path}.tmp"
            with open(temp_path, "w", encoding="utf-8") as stream:
                json.dump(existing, stream, ensure_ascii=False, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, file_path)

    def _update_impl(self, event):
        return None
