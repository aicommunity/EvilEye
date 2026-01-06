import time
from .db_adapter import DatabaseAdapterBase
import copy
import datetime
import os
import cv2
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql


class DatabaseAdapterFieldOfViewEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)
        self.image_dir = self.db_params['image_dir']
        self.preview_width = self.db_params['preview_width']
        self.preview_height = self.db_params['preview_height']
        self.preview_size = (self.preview_width, self.preview_height)

    def set_params_impl(self):
        super().set_params_impl()
        self.event_name = self.params['event_name']

    def _insert_impl(self, event):
        fields, data, preview_path = self._prepare_for_saving(event)
        query_type = 'insert'
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path))

    def _update_impl(self, event):
        fields, data, preview_path = self._prepare_for_updating(event)

        query_type = 'update'
        data.append(event.event_id)
        data = tuple(data)
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE event_id=({selected})').format(
            table=sql.Identifier(self.table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put((query_type, update_query, data, preview_path))

    def _execute_query(self):
        while self.run_flag:
            time.sleep(0.01)
            try:
                if not self.queue_in.empty():
                    query_type, query_string, data, preview_path = self.queue_in.get()
                    if query_string is not None:
                        pass
                else:
                    query_type = query_string = data = preview_path = None
            except ValueError:
                break

            if query_string is None:
                continue

            try:
                record = self.db_controller.query(query_string, data)
            except Exception as e:
                # Attempt to auto-migrate missing columns and retry once
                msg = str(e)
                if 'UndefinedColumn' in msg or 'does not exist' in msg:
                    try:
                        self._ensure_fov_columns()
                        self.logger.warning('DB: Missing columns in fov_events detected. Applied auto-migration. Retrying query...')
                        record = self.db_controller.query(query_string, data)
                    except Exception as e2:
                        self.logger.error(f'DB: FOVEvents query failed after migration attempt: {e2}')
                        continue
                else:
                    self.logger.error(f'DB: FOVEvents query failed: {e}')
                    continue
            # row_num = record[0][0]
            if query_type == 'insert':
                threading_events.notify('new event')
            elif query_type == 'update':
                threading_events.notify('update event')

    def _save_image(self, preview_path, frame_path, image, box):
        preview_save_dir = os.path.join(self.image_dir, preview_path)
        frame_save_dir = os.path.join(self.image_dir, frame_path)
        preview = cv2.resize(copy.deepcopy(image.image), self.preview_size, cv2.INTER_NEAREST)
        preview_boxes = utils.draw_preview_boxes(preview, self.preview_width, self.preview_height, box)
        preview_saved = cv2.imwrite(preview_save_dir, preview_boxes)
        frame_saved = cv2.imwrite(frame_save_dir, image.image)
        if not preview_saved or not frame_saved:
            self.logger.error(f'ERROR: can\'t save image file {frame_save_dir}')

    def _prepare_for_updating(self, event):
        fields_for_updating = {'time_lost': event.time_lost,
                               'lost_preview_path': '',
                               'video_path_lost': getattr(event, 'video_path_lost', None)}

        src_name = ''
        for camera in self.cameras_params:
            if event.source_id in camera['source_ids']:
                id_idx = camera['source_ids'].index(event.source_id)
                src_name = camera['source_names'][id_idx]
                break

        fields_for_updating['lost_preview_path'] = self._get_img_path('preview', 'lost', src_name, time_lost=event.time_lost)

        return (list(fields_for_updating.keys()), list(fields_for_updating.values()),
                fields_for_updating['lost_preview_path'])

    def _prepare_for_saving(self, event) -> tuple[list, list, str]:
        fields_for_saving = {'event_id': event.event_id,
                             'source_id': event.source_id,
                             'time_stamp': event.timestamp,
                             'time_obj_detected': event.time_obj_detected,
                             'time_lost': event.time_lost,
                             'object_id': event.object_id,
                             'preview_path': '',
                             'lost_preview_path': None,
                             'video_path': getattr(event, 'video_path', None),
                             'video_path_lost': None,
                             'project_id': self.db_controller.get_project_id(),
                             'job_id': self.db_controller.get_job_id()}
        src_name = ''
        for camera in self.cameras_params:
            if event.source_id in camera['source_ids']:
                id_idx = camera['source_ids'].index(event.source_id)
                src_name = camera['source_names'][id_idx]
                break
        fields_for_saving['preview_path'] = self._get_img_path('preview', 'detected', src_name, event.time_obj_detected)
        if event.time_lost is not None:
            fields_for_saving['lost_preview_path'] = self._get_img_path('preview', 'lost', src_name, time_lost=event.time_lost)
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()),
                fields_for_saving['preview_path'])

    def _get_img_path(self, image_type, obj_event_type, src_name, time_stamp=None, time_lost=None):
        save_dir = self.db_params['image_dir']
        events_dir = os.path.join(save_dir, 'Events')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y-%m-%d')

        current_day_path = os.path.join(events_dir, cur_date_str)
        images_dir = os.path.join(current_day_path, 'Images')
        # New folders for events: FoundFrames/FoundPreviews/LostFrames/LostPreviews
        if obj_event_type == 'detected':
            if image_type == 'preview':
                subdir = 'FoundPreviews'
            else:
                subdir = 'FoundFrames'
        else:  # lost
            if image_type == 'preview':
                subdir = 'LostPreviews'
            else:
                subdir = 'LostFrames'
        obj_type_path = os.path.join(images_dir, subdir)

        if not os.path.exists(events_dir):
            os.makedirs(events_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(images_dir):
            os.makedirs(images_dir, exist_ok=True)
        if not os.path.exists(obj_type_path):
            os.makedirs(obj_type_path, exist_ok=True)

        if obj_event_type == 'detected':
            timestamp = time_stamp.strftime('%Y-%m-%d_%H-%M-%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{src_name}_{image_type}.jpeg')
        elif obj_event_type == 'lost':
            timestamp = time_lost.strftime('%Y-%m-%d_%H-%M-%S-%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{src_name}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)

    def _ensure_fov_columns(self):
        # Ensure newly added columns exist in fov_events table
        try:
            alter_tpl = "ALTER TABLE {} ADD COLUMN IF NOT EXISTS {} {};"
            table = self.table_name
            # List of required columns and types
            required = [
                ('video_path', 'text'),
                ('video_path_lost', 'text'),
            ]
            for col, coltype in required:
                query = alter_tpl.format(table, col, coltype)
                self.db_controller.query(query, None)
        except Exception as e:
            self.logger.error(f'DB: Failed to ensure fov_events columns: {e}')
