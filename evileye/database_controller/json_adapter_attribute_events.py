import os
import json
import datetime
from .db_adapter import DatabaseAdapterBase
import copy
import cv2


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
        self.base_dir = os.path.join(self.image_dir, 'images')
        self.table_name = 'attribute_events_json'
        self.event_name = 'AttributeEvent'

    def init_impl(self):
        os.makedirs(self.base_dir, exist_ok=True)

    def start(self):
        # no thread needed
        self.run_flag = True

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
            date_folder = event_dt.date().strftime('%Y_%m_%d')
            day_dir = os.path.join(self.base_dir, date_folder)
            os.makedirs(day_dir, exist_ok=True)
            file_name = 'attribute_events_finished.json' if is_update else 'attribute_events_found.json'
            file_path = os.path.join(day_dir, file_name)

            data = []
            if os.path.isfile(file_path):
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        data = json.load(f) or []
                except Exception:
                    data = []

            # Normalize box relative to source image size if available
            box = event.box_finished if is_update else event.box_found
            img = getattr(event, 'img_finished', None) if is_update else getattr(event, 'img_found', None)
            if box and img is not None and hasattr(img, 'image'):
                ih, iw = img.image.shape[:2]
                bx, by, bw, bh = box
                if iw and ih:
                    box = [bx/iw, by/ih, bw/iw, bh/ih]

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

            data.append(rec)
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
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
            # Унифицированные каталоги: events_found_* / events_lost_*
            tag = 'events_lost' if is_update else 'events_found'
            ts = (event.get_time_finished() if is_update else event.timestamp)
            if ts is None:
                ts = datetime.datetime.now()
            # Имя с тем же форматом, как и в других адаптерах
            ts_str = ts.strftime('%Y_%m_%d_%H_%M_%S_%f') if is_update else ts.strftime('%Y_%m_%d_%H_%M_%S.%f')
            previews_dir = os.path.join(day_dir, f'{tag}_previews')
            frames_dir = os.path.join(day_dir, f'{tag}_frames')
            os.makedirs(previews_dir, exist_ok=True)
            os.makedirs(frames_dir, exist_ok=True)

            image_wrap = getattr(event, 'img_finished', None) if is_update else getattr(event, 'img_found', None)
            if image_wrap is None or not hasattr(image_wrap, 'image'):
                return '', ''

            preview = cv2.resize(copy.deepcopy(image_wrap.image), (320, 240), cv2.INTER_NEAREST)
            preview_name = f'{ts_str}_src{event.source_id}_attribute_preview.jpeg'
            frame_name = f'{ts_str}_src{event.source_id}_attribute_frame.jpeg'
            cv2.imwrite(os.path.join(previews_dir, preview_name), preview)
            cv2.imwrite(os.path.join(frames_dir, frame_name), image_wrap.image)
            # Пути относительно image_dir
            preview_rel = os.path.relpath(os.path.join(previews_dir, preview_name), self.image_dir)
            frame_rel = os.path.relpath(os.path.join(frames_dir, frame_name), self.image_dir)
            return preview_rel, frame_rel
        except Exception:
            return '', ''


