import time
from .db_adapter import DatabaseAdapterBase
from .constants import QueryType, EventType
from ..utils.utils import ObjectResultEncoder
import copy
import datetime
import os
from timeit import default_timer as timer
import cv2
import numpy as np
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql
from .event_image_writer import EventImageWriter


class DatabaseAdapterZoneEvents(DatabaseAdapterBase):
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
        fields, data, preview_path, frame_path = self._prepare_for_saving(event)
        query_type = QueryType.INSERT
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING box_entered, zone_coords").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path, frame_path, event.img_entered))

    def _update_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_updating(event)

        query_type = QueryType.UPDATE
        # Надёжный поиск последней незавершённой записи события зоны
        # Ключ: (project_id, job_id, source_id, object_id, zone_coords), сортировка по time_entered DESC
        project_id = self.db_controller.get_project_id()
        job_id = self.db_controller.get_job_id()
        where_query = sql.SQL(
            'SELECT event_id FROM {table} '
            'WHERE project_id = %s AND job_id = %s AND source_id = %s AND object_id = %s '
            'ORDER BY (zone_coords = %s::real[][]) DESC, time_entered DESC NULLS LAST LIMIT 1'
        ).format(table=sql.Identifier(self.table_name))

        # Параметры WHERE идут после данных SET
        # Координаты для сравнения в ORDER BY приводим к тому же округлению
        zone_coords_param = [[round(p[0], 4), round(p[1], 4)] for p in event.zone.get_coords()]
        data = tuple(data) + (
            project_id,
            job_id,
            event.source_id,
            event.object_id,
            zone_coords_param,
        )

        update_query = sql.SQL(
            'UPDATE {table} SET {data} WHERE event_id = ({selected}) RETURNING box_left, zone_coords'
        ).format(
            table=sql.Identifier(self.table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(' = '), sql.Placeholder()]) for field in fields
            ),
            selected=where_query
        )
        self.queue_in.put((query_type, update_query, data, preview_path, frame_path, event.img_left))

    def _execute_query(self):
        while self.run_flag:
            time.sleep(0.01)
            try:
                if not self.queue_in.empty():
                    query_type, query_string, data, preview_path, frame_path, image = self.queue_in.get()
                    if query_string is not None:
                        pass
                else:
                    query_type = query_string = data = preview_path = frame_path = image = None
            except ValueError:
                break

            if query_string is None:
                continue

            self._process_queue_item((query_type, query_string, data, preview_path, frame_path, image))

    def _process_queue_item(self, item):
        query_type, query_string, data, preview_path, frame_path, image = item

        try:
            record = self.db_controller.query(query_string, data)
        except Exception as e:
            self.logger.error(f'DB: ZoneEvents query failed: {e}')
            return

        # Безопасные проверки результата RETURNING
        if not record:
            if query_type == QueryType.INSERT:
                self.logger.warning('DB: ZoneEvents INSERT returned no data; skipping image save')
            return

        if not isinstance(record, list) or len(record) == 0:
            if query_type == QueryType.INSERT:
                self.logger.warning('DB: ZoneEvents INSERT returned empty list; skipping image save')
            return

        if not record[0] or len(record[0]) < 2:
            self.logger.warning(f'DB: ZoneEvents query returned incomplete data: {record}; skipping image save')
            return

        box = record[0][0]
        zone_coords = record[0][1]

        if box is None or zone_coords is None:
            self.logger.warning('DB: Missing box/zone_coords in RETURNING; skipping image save')
            return

        if not isinstance(box, (list, tuple, np.ndarray)):
            self.logger.warning(
                f'DB: Invalid box type in RETURNING: {type(box)}, expected list/tuple/array; skipping image save'
            )
            return

        if len(box) < 4:
            self.logger.warning(
                f'DB: Invalid box format in RETURNING: {box}, expected [x1, y1, x2, y2]; skipping image save'
            )
            return

        if image is None:
            self.logger.warning('DB: Image is None in RETURNING; skipping image save')
            return

        self._save_image(preview_path, frame_path, image, box, zone_coords)

        if query_type == QueryType.INSERT:
            threading_events.notify(EventType.NEW_EVENT)
        elif query_type == QueryType.UPDATE:
            threading_events.notify(EventType.UPDATE_EVENT)

    def _save_image(self, preview_path, frame_path, image, box, zone_coords):
        self._event_image_writer.save(
            preview_path, frame_path, image, box=box, zone_coords=zone_coords
        )

    def _prepare_for_updating(self, event):
        fields_for_updating = {'time_left': event.time_left,
                               'box_left': event.box_left,
                               'frame_path_left': self._get_img_path('frame', 'zone_left', event, time_lost=event.time_left),
                               'preview_path_left': self._get_img_path('preview', 'zone_left', event, time_lost=event.time_left),
                               'video_path_left': getattr(event, 'video_path_left', None)}

        if event.box_left is not None and event.img_left is not None and hasattr(event.img_left, 'image'):
            image_height, image_width, _ = event.img_left.image.shape
            # Use list() instead of deepcopy for bounding box (list of numbers)
            fields_for_updating['box_left'] = list(fields_for_updating['box_left'])
            fields_for_updating['box_left'][0] /= image_width
            fields_for_updating['box_left'][1] /= image_height
            fields_for_updating['box_left'][2] /= image_width
            fields_for_updating['box_left'][3] /= image_height
        return (list(fields_for_updating.keys()), list(fields_for_updating.values()),
                fields_for_updating['preview_path_left'], fields_for_updating['frame_path_left'])

    def _prepare_for_saving(self, event) -> tuple[list, list, str, str]:
        fields_for_saving = {'event_id': event.event_id,
                             'source_id': event.source_id,
                             'time_entered': event.time_entered,
                             'time_left': event.time_left,
                             'object_id': event.object_id,
                             'box_entered': event.box_entered,
                             'box_left': None,
                             'zone_coords': None,
                             'frame_path_entered': self._get_img_path('frame', 'zone_entered', event, event.time_entered),
                             'frame_path_left': None,
                             'preview_path_entered': self._get_img_path('preview', 'zone_entered', event, event.time_entered),
                             'preview_path_left': None,
                             'video_path_entered': getattr(event, 'video_path_entered', None),
                             'video_path_left': None,
                             'project_id': self.db_controller.get_project_id(),
                             'job_id': self.db_controller.get_job_id()}

        # Нормализуем координаты зоны, чтобы избежать ошибок сравнения float
        coords = [list(point) for point in event.zone.get_coords()]
        coords_rounded = [[round(p[0], 4), round(p[1], 4)] for p in coords]
        fields_for_saving['zone_coords'] = coords_rounded

        image_height, image_width, _ = event.img_entered.image.shape
        # Use list() instead of deepcopy for bounding box (list of numbers)
        fields_for_saving['box_entered'] = list(fields_for_saving['box_entered'])
        fields_for_saving['box_entered'][0] /= image_width
        fields_for_saving['box_entered'][1] /= image_height
        fields_for_saving['box_entered'][2] /= image_width
        fields_for_saving['box_entered'][3] /= image_height
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()),
                fields_for_saving['preview_path_entered'], fields_for_saving['frame_path_entered'])

    def _get_img_path(self, image_type, obj_event_type, event, time_stamp=None, time_lost=None):
        save_dir = self.db_params['image_dir']
        events_dir = os.path.join(save_dir, 'Events')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y-%m-%d')

        current_day_path = os.path.join(events_dir, cur_date_str)
        images_dir = os.path.join(current_day_path, 'Images')
        # New folders for events: FoundFrames/FoundPreviews/LostFrames/LostPreviews
        if obj_event_type == 'zone_entered':
            if image_type == 'preview':
                subdir = 'FoundPreviews'
            else:
                subdir = 'FoundFrames'
        else:  # zone_left
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

        zone_id = event.zone.get_zone_id()
        obj_id = event.object_id
        if obj_event_type == 'zone_entered':
            timestamp = time_stamp.strftime('%Y-%m-%d_%H-%M-%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_zone{zone_id}_obj{obj_id}_{image_type}.jpeg')
        elif obj_event_type == 'zone_left':
            timestamp = time_lost.strftime('%Y-%m-%d_%H-%M-%S-%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_zone{zone_id}_obj{obj_id}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)

    # NOTE: schema migrations are applied centrally at DB startup (see `database_controller/migrations.py`).
