import os
import json
import datetime
import copy
import cv2
from .db_adapter import DatabaseAdapterBase


class JsonAdapterZoneEvents(DatabaseAdapterBase):
    """Persist Zone events to JSON files and save images (original frames)."""

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
        self.event_name = 'ZoneEvent'
        self.table_name = 'zone_events_json'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def start(self):
        self.run_flag = True

    def stop(self):
        self.run_flag = False

    def _execute_query(self):
        pass

    def _insert_impl(self, event):
        self._write_event(event, is_update=False)

    def _update_impl(self, event):
        self._write_event(event, is_update=True)

    def _write_event(self, event, is_update: bool):
        date_folder = datetime.date.today().strftime('%Y_%m_%d')
        day_dir = os.path.join(self.base_dir, date_folder)
        os.makedirs(day_dir, exist_ok=True)
        file_name = 'zone_events_left.json' if is_update else 'zone_events_entered.json'
        file_path = os.path.join(day_dir, file_name)

        records = []
        if os.path.isfile(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    records = json.load(f) or []
            except Exception:
                records = []

        ts = (event.time_left or event.time_entered)
        preview_rel, frame_rel = self._save_images(day_dir, event, is_update)

        # Normalize box if present using source image
        box = event.box_left if is_update else event.box_entered
        img = event.img_left if is_update else event.img_entered
        if box and img is not None and hasattr(img, 'image'):
            ih, iw = img.image.shape[:2]
            bx, by, bw, bh = box
            if iw and ih:
                box = [bx/iw, by/ih, bw/iw, bh/ih]

        rec = {
            'event_id': event.event_id,
            'ts': ts.isoformat() if hasattr(ts, 'isoformat') else str(ts),
            'source_id': event.source_id,
            'object_id': event.object_id,
            'zone_id': event.zone.get_zone_id() if hasattr(event, 'zone') else None,
            'box': box,
            'zone_coords': [list(p) for p in event.zone.get_coords()] if hasattr(event, 'zone') else None,
            'preview_path': preview_rel,
            'frame_path': frame_rel,
        }
        records.append(rec)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(records, f, ensure_ascii=False, indent=2)

    def _save_images(self, day_dir: str, event, is_update: bool):
        # Унифицированные каталоги: events_found_* / events_lost_*
        tag = 'events_lost' if is_update else 'events_found'
        ts = (event.time_left if is_update else event.time_entered)
        ts_str = ts.strftime('%Y_%m_%d_%H_%M_%S_%f') if is_update else ts.strftime('%Y_%m_%d_%H_%M_%S.%f')
        previews_dir = os.path.join(day_dir, f'{tag}_previews')
        frames_dir = os.path.join(day_dir, f'{tag}_frames')
        os.makedirs(previews_dir, exist_ok=True)
        os.makedirs(frames_dir, exist_ok=True)

        image = event.img_left if is_update else event.img_entered
        if image is None or not hasattr(image, 'image'):
            return '', ''

        preview = cv2.resize(copy.deepcopy(image.image), (320, 240), cv2.INTER_NEAREST)
        preview_name = f'{ts_str}_src{event.source_id}_zone{event.zone.get_zone_id()}_preview.jpeg'
        frame_name = f'{ts_str}_src{event.source_id}_zone{event.zone.get_zone_id()}_frame.jpeg'
        cv2.imwrite(os.path.join(previews_dir, preview_name), preview)
        cv2.imwrite(os.path.join(frames_dir, frame_name), image.image)
        preview_rel = os.path.relpath(os.path.join(previews_dir, preview_name), self.image_dir)
        frame_rel = os.path.relpath(os.path.join(frames_dir, frame_name), self.image_dir)
        return preview_rel, frame_rel


