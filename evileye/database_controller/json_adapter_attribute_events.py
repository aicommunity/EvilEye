import os
import datetime
from .db_adapter import DatabaseAdapterBase
from .json_event_io import append_json_record
from .event_image_paths import ensure_event_image_dirs
import copy
import cv2

from .image_storage_service import ImageStorageService


class JsonAdapterAttributeEvents(DatabaseAdapterBase):
    """Adapter that persists attribute events to JSON files for JSON journal."""

    def __init__(self, db_controller=None):
        # Важно: сначала определить поля, затем вызывать super().__init__(self),
        # потому что базовый конструктор вызывает get_params() контроллера.
        self.image_dir = None
        self.base_dir = None
        # db_controller is unused; keep base api
        super().__init__(db_controller or self)

    # Dummy implementations to satisfy base
    def get_params(self):
        return {'image_dir': self.image_dir}

    # JSON режим: камерные параметры не используются
    def get_cameras_params(self):
        return {}

    def set_params_impl(self):
        # prefer controller.database.image_dir if present
        self.image_dir = self.params.get('image_dir', 'EvilEyeData')
        self.base_dir = os.path.join(self.image_dir, 'Events')
        self.table_name = 'attribute_events_json'
        self.event_name = 'AttributeEvent'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)
        # Keep preview dimensions consistent with legacy JSON adapters (320x240)
        self._image_storage = ImageStorageService(self.image_dir, preview_width=320, preview_height=240, logger=None)

    def start(self):
        # no thread needed
        self.run_flag = True

    def _process_queue_item(self, item):
        """JSON адаптер не использует очередь; метод требуется базовым классом."""
        return

    def stop(self):
        self.run_flag = False

    def _execute_query(self):
        # not used
        pass

    def _insert_impl(self, event):
        self._write_event(event, is_update=False)

    def _update_impl(self, event):
        self._write_event(event, is_update=True)

    def _write_event(self, event, is_update: bool):
        try:
            # Используем дату события (а не текущую), чтобы файлы попадали в ту же папку даты, что и другие JSON
            try:
                event_dt = getattr(event, 'get_time_finished', None)() or getattr(event, 'timestamp', None)
            except Exception:
                event_dt = getattr(event, 'timestamp', None)
            if event_dt is None:
                event_dt = datetime.datetime.now()
            date_folder = event_dt.date().strftime('%Y-%m-%d')
            day_dir = os.path.join(self.base_dir, date_folder)
            metadata_dir = os.path.join(day_dir, 'Metadata')
            os.makedirs(metadata_dir, exist_ok=True)
            file_name = 'attribute_events_finished.json' if is_update else 'attribute_events_found.json'
            file_path = os.path.join(metadata_dir, file_name)

            # Normalize box relative to source image size if available
            box = event.box_finished if is_update else event.box_found
            img = getattr(event, 'img_finished', None) if is_update else getattr(event, 'img_found', None)
            if box and img is not None and hasattr(img, 'image'):
                ih, iw = img.image.shape[:2]
                x1, y1, x2, y2 = box
                if iw and ih:
                    box = [x1 / iw, y1 / ih, x2 / iw, y2 / ih]

            # Save preview and full frame images (pure, без оверлеев) в унифицированные папки
            preview_rel, frame_rel = self._save_images(day_dir, event, is_update)

            rec = {
                'event_id': event.event_id,
                'ts': (event.get_time_finished() or event.timestamp).isoformat(),
                'source_id': event.source_id,
                'object_id': event.object_id,
                'event_name': event.matched_event_name,
                'attrs': event.matched_attrs,
                'class_id': event.class_id,
                'box': box,
                'preview_path': preview_rel or '',
                'frame_path': frame_rel or '',
            }

            append_json_record(file_path, rec)
            # Простая диагностика на запись события
            try:
                from evileye.core.logger import get_module_logger
                get_module_logger('json_adapter_attribute_events').info(
                    f"JSON AttributeEvent saved: file={file_name} name={rec.get('event_name')} obj={rec.get('object_id')} ts={rec.get('ts')}")
            except Exception:
                pass
        except Exception as e:
            # best-effort
            pass

    def _save_images(self, day_dir: str, event, is_update: bool):
        try:
            # Новые каталоги: Events/.../Images/FoundFrames/FoundPreviews/LostFrames/LostPreviews
            ts = (event.get_time_finished() if is_update else event.timestamp)
            if ts is None:
                ts = datetime.datetime.now()
            # Имя с новым форматом без подчеркиваний в дате
            ts_str = ts.strftime('%Y-%m-%d_%H-%M-%S-%f') if is_update else ts.strftime('%Y-%m-%d_%H-%M-%S.%f')
            previews_dir, frames_dir = ensure_event_image_dirs(day_dir, is_lost=is_update)

            image_wrap = getattr(event, 'img_finished', None) if is_update else getattr(event, 'img_found', None)
            if image_wrap is None or not hasattr(image_wrap, 'image'):
                return '', ''

            preview_name = f'{ts_str}_src{event.source_id}_attribute_preview.jpeg'
            frame_name = f'{ts_str}_src{event.source_id}_attribute_frame.jpeg'
            preview_abs = os.path.join(previews_dir, preview_name)
            frame_abs = os.path.join(frames_dir, frame_name)

            preview_rel = os.path.relpath(preview_abs, self.image_dir)
            frame_rel = os.path.relpath(frame_abs, self.image_dir)

            # Centralized save (creates dirs)
            if getattr(self, "_image_storage", None):
                self._image_storage.save_image_simple(preview_rel, frame_rel, image_wrap)
            else:
                preview = ImageStorageService.resize_preserving_aspect(image_wrap.image.copy(), 320, 240)
                cv2.imwrite(preview_abs, preview)
                cv2.imwrite(frame_abs, image_wrap.image)
            # Пути относительно image_dir
            return preview_rel, frame_rel
        except Exception:
            return '', ''
