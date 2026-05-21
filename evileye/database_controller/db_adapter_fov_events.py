import time
from .db_adapter import DatabaseAdapterBase
from .constants import QueryType, EventType
import copy
import datetime
import os
import cv2
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql
from .event_image_writer import EventImageWriter


class DatabaseAdapterFieldOfViewEvents(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)
        self.image_dir = self.db_params['image_dir']
        self.preview_width = self.db_params['preview_width']
        self.preview_height = self.db_params['preview_height']
        self.preview_size = (self.preview_width, self.preview_height)
        self._event_image_writer = EventImageWriter(
            self.image_dir,
            self.preview_width,
            self.preview_height,
            db_controller=self.db_controller,
            logger=self.logger,
        )

    def set_params_impl(self):
        super().set_params_impl()
        self.event_name = self.params['event_name']

    def _insert_impl(self, event):
        fields, data, preview_path = self._prepare_for_saving(event)
        query_type = QueryType.INSERT
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({})").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path))

    def _update_impl(self, event):
        fields, data, preview_path = self._prepare_for_updating(event)

        query_type = QueryType.UPDATE
        data.append(event.event_id)
        data = tuple(data)
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE event_id=({selected})').format(
            table=sql.Identifier(self.table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put((query_type, update_query, data, preview_path))

    def _process_queue_item(self, item):
        query_type, query_string, data, preview_path = item

        if query_string is None:
            return

        try:
            record = self.db_controller.query(query_string, data)
        except Exception as e:
            should_retry, last_error = self.error_handler.handle_query_error(
                error=e,
                query_string=str(query_string) if query_string else None,
                retry_callback=None,
                max_retries=1,
            )
            if last_error:
                return
            record = self.db_controller.query(query_string, data)
        if query_type == QueryType.INSERT:
            threading_events.notify(EventType.NEW_EVENT)
        elif query_type == QueryType.UPDATE:
            threading_events.notify(EventType.UPDATE_EVENT)

    def _save_image(self, preview_path, frame_path, image, box):
        self._event_image_writer.save(preview_path, frame_path, image, box=box)

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

    # NOTE: schema migrations are applied centrally at DB startup (see `database_controller/migrations.py`).
