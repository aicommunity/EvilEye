import os
import datetime
from .json_event_io import append_json_record
from .event_image_paths import ensure_event_image_dirs
import copy
import cv2
from .db_adapter import DatabaseAdapterBase
from .image_storage_service import ImageStorageService


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
        self.base_dir = os.path.join(self.image_dir, 'Events')
        self.event_name = 'ZoneEvent'
        self.table_name = 'zone_events_json'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)
        # Keep preview dimensions consistent with legacy JSON adapters (320x240)
        self._image_storage = ImageStorageService(self.image_dir, preview_width=320, preview_height=240, logger=None)

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
        self._write_event(event, is_update=False)

    def _update_impl(self, event):
        self._write_event(event, is_update=True)

    def _write_event(self, event, is_update: bool):
        date_folder = datetime.date.today().strftime('%Y-%m-%d')
        day_dir = os.path.join(self.base_dir, date_folder)
        metadata_dir = os.path.join(day_dir, 'Metadata')
        os.makedirs(metadata_dir, exist_ok=True)
        file_name = 'zone_events_left.json' if is_update else 'zone_events_entered.json'
        file_path = os.path.join(metadata_dir, file_name)

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
        append_json_record(file_path, rec)

    def _save_images(self, day_dir: str, event, is_update: bool):
        # Новые каталоги: Events/.../Images/FoundFrames/FoundPreviews/LostFrames/LostPreviews
        ts = (event.time_left if is_update else event.time_entered)
        ts_str = ts.strftime('%Y-%m-%d_%H-%M-%S-%f') if is_update else ts.strftime('%Y-%m-%d_%H-%M-%S.%f')
        previews_dir, frames_dir = ensure_event_image_dirs(day_dir, is_lost=is_update)

        image = event.img_left if is_update else event.img_entered
        if image is None or not hasattr(image, 'image'):
            return '', ''

        preview_name = f'{ts_str}_src{event.source_id}_zone{event.zone.get_zone_id()}_preview.jpeg'
        frame_name = f'{ts_str}_src{event.source_id}_zone{event.zone.get_zone_id()}_frame.jpeg'
        preview_abs = os.path.join(previews_dir, preview_name)
        frame_abs = os.path.join(frames_dir, frame_name)

        preview_rel = os.path.relpath(preview_abs, self.image_dir)
        frame_rel = os.path.relpath(frame_abs, self.image_dir)

        if getattr(self, "_image_storage", None):
            self._image_storage.save_image_simple(preview_rel, frame_rel, image)
        else:
            preview = cv2.resize(image.image.copy(), (320, 240), cv2.INTER_NEAREST)
            cv2.imwrite(preview_abs, preview)
            cv2.imwrite(frame_abs, image.image)
        return preview_rel, frame_rel


