import time
from .db_adapter import DatabaseAdapterBase
from ..utils import threading_events
from ..utils import utils
import os
import copy
import cv2
from psycopg2 import sql


class DatabaseAdapterAttributeEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)

    def set_params_impl(self):
        super().set_params_impl()
        # event_name must match AttributeEvent.get_name()
        self.event_name = self.params['event_name']

    def _insert_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_saving(event)
        query_type = 'insert'
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path, frame_path, getattr(event, 'img_found', None), getattr(event, 'box_found', None)))

    def _update_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_updating(event)
        query_type = 'update'
        data.append(event.event_id)
        data = tuple(data)
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE event_id=({selected})').format(
            table=sql.Identifier(self.table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put((query_type, update_query, data, preview_path, frame_path, getattr(event, 'img_finished', None), getattr(event, 'box_finished', None)))

    def _execute_query(self):
        while self.run_flag:
            time.sleep(0.01)
            try:
                if not self.queue_in.empty():
                    query_type, query_string, data, preview_path, frame_path, image, box = self.queue_in.get()
                    if query_string is not None:
                        pass
                else:
                    query_type = query_string = data = preview_path = frame_path = image = box = None
            except ValueError:
                break

            if query_string is None:
                continue

            try:
                self.db_controller.query(query_string, data)
            except Exception as e:
                # Attempt to auto-migrate missing columns and retry once
                msg = str(e)
                if 'UndefinedColumn' in msg or 'does not exist' in msg:
                    try:
                        self._ensure_attribute_columns()
                        self.logger.warning('DB: Missing columns in attribute_events detected. Applied auto-migration. Retrying query...')
                        self.db_controller.query(query_string, data)
                    except Exception as e2:
                        self.logger.error(f'DB: AttributeEvents query failed after migration attempt: {e2}')
                        continue
                else:
                    self.logger.error(f'DB: AttributeEvents query failed: {e}')
                    continue
            # Save images if available
            try:
                if image is not None and preview_path is not None and frame_path is not None and box is not None:
                    self._save_image(preview_path, frame_path, image, box)
            except Exception:
                pass
            # Log success write - removed to reduce log noise
            if query_type == 'insert':
                threading_events.notify('new event')
            elif query_type == 'update':
                threading_events.notify('update event')

    def _prepare_for_saving(self, event) -> tuple[list, list, str, str]:
        # Payload with image paths for attribute event START
        fields_for_saving = {
            'event_id': event.event_id,
            'source_id': event.source_id,
            'time_stamp': event.timestamp,
            'time_finished': event.get_time_finished(),
            'object_id': event.object_id,
            'event_name': event.matched_event_name,
            'attrs': ','.join(event.matched_attrs),
            'class_id': event.class_id if event.class_id is not None else -1,
            'box_found': None,
            'box_finished': None,
            'preview_path_found': '',
            'frame_path_found': ''
        }
        # Normalize and set box_found if available
        if event.box_found is not None and event.img_found is not None and hasattr(event.img_found, 'image'):
            ih, iw, _ = event.img_found.image.shape
            box = list(event.box_found)
            norm_box = [box[0]/iw, box[1]/ih, box[2]/iw, box[3]/ih]
            fields_for_saving['box_found'] = norm_box
        preview_path = self._get_img_path('preview', 'attribute_found', event, event.time_found)
        frame_path = self._get_img_path('frame', 'attribute_found', event, event.time_found)
        fields_for_saving['preview_path_found'] = preview_path
        fields_for_saving['frame_path_found'] = frame_path
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()), preview_path, frame_path)

    def _prepare_for_updating(self, event):
        # Update finish timestamp and image paths on event completion
        fields_for_updating = {
            'time_finished': event.get_time_finished(),
            'box_finished': None,
            'preview_path_finished': self._get_img_path('preview', 'attribute_finished', event, time_lost=event.get_time_finished()),
            'frame_path_finished': self._get_img_path('frame', 'attribute_finished', event, time_lost=event.get_time_finished())
        }
        if event.box_finished is not None and event.img_finished is not None and hasattr(event.img_finished, 'image'):
            ih, iw, _ = event.img_finished.image.shape
            box = list(event.box_finished)
            norm_box = [box[0]/iw, box[1]/ih, box[2]/iw, box[3]/ih]
            fields_for_updating['box_finished'] = norm_box
        return (list(fields_for_updating.keys()), list(fields_for_updating.values()), fields_for_updating['preview_path_finished'], fields_for_updating['frame_path_finished'])

    def _save_image(self, preview_path, frame_path, image, box):
        save_dir = self.db_params['image_dir']
        preview_save_dir = os.path.join(save_dir, preview_path)
        frame_save_dir = os.path.join(save_dir, frame_path)
        # Build preview
        try:
            preview_width = self.db_params.get('preview_width', 300)
            preview_height = self.db_params.get('preview_height', 150)
            # Save original (no debug overlays) for both preview and frame
            preview = cv2.resize(copy.deepcopy(image.image), (preview_width, preview_height), cv2.INTER_NEAREST)
            os.makedirs(os.path.dirname(preview_save_dir), exist_ok=True)
            os.makedirs(os.path.dirname(frame_save_dir), exist_ok=True)
            cv2.imwrite(preview_save_dir, preview)
            cv2.imwrite(frame_save_dir, image.image)
        except Exception as e:
            self.logger.error(f"Attribute event image saving error: {e}")

    def _get_img_path(self, image_type, obj_event_type, event, time_stamp=None, time_lost=None):
        save_dir = self.db_params['image_dir']
        img_dir = os.path.join(save_dir, 'images')
        import datetime
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y_%m_%d')

        current_day_path = os.path.join(img_dir, cur_date_str)
        # Unified folders for events: events_found_*/events_lost_* (frames/previews)
        if obj_event_type == 'attribute_found':
            tag = 'events_found'
        elif obj_event_type == 'attribute_finished':
            tag = 'events_lost'
        else:
            tag = obj_event_type
        subdir = f"{tag}_{'previews' if image_type == 'preview' else 'frames'}"
        obj_type_path = os.path.join(current_day_path, subdir)

        if not os.path.exists(img_dir):
            os.makedirs(img_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(obj_type_path):
            os.makedirs(obj_type_path, exist_ok=True)

        obj_id = event.object_id
        if obj_event_type == 'attribute_found':
            timestamp = (time_stamp or event.timestamp).strftime('%Y_%m_%d_%H_%M_%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_attr_{event.matched_event_name}_obj{obj_id}_{image_type}.jpeg')
        elif obj_event_type == 'attribute_finished':
            ts = (time_lost or event.get_time_finished())
            timestamp = ts.strftime('%Y_%m_%d_%H_%M_%S_%f') if ts else 'unknown'
            img_path = os.path.join(obj_type_path, f'{timestamp}_attr_{event.matched_event_name}_obj{obj_id}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)

    def _ensure_attribute_columns(self):
        # Ensure newly added columns exist in attribute_events table
        try:
            alter_tpl = "ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {};"
            table = self.table_name
            # List of required columns and types
            required = [
                ('preview_path_found', 'text'),
                ('frame_path_found', 'text'),
                ('preview_path_finished', 'text'),
                ('frame_path_finished', 'text'),
                ('class_id', 'integer'),
                ('box_found', 'real[]'),
                ('box_finished', 'real[]')
            ]
            for col, coltype in required:
                query = alter_tpl.format(table, col, coltype)
                self.db_controller.query(query, None)
        except Exception as e:
            self.logger.error(f'DB: Failed to ensure attribute_events columns: {e}')


