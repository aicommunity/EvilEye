import time
from .db_adapter import DatabaseAdapterBase
from ..utils.utils import ObjectResultEncoder
import copy
import datetime
import os
from timeit import default_timer as timer
import cv2
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql


class DatabaseAdapterZoneEvents(DatabaseAdapterBase):
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
        fields, data, preview_path, frame_path = self._prepare_for_saving(event)
        query_type = 'insert'
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING box_entered, zone_coords").format(
            sql.Identifier(self.table_name),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path, frame_path, event.img_entered))

    def _update_impl(self, event):
        fields, data, preview_path, frame_path = self._prepare_for_updating(event)

        query_type = 'update'
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

            try:
                record = self.db_controller.query(query_string, data)
            except Exception as e:
                self.logger.error(f'DB: ZoneEvents query failed: {e}')
                continue

            # Безопасные проверки результата RETURNING
            if not record or not isinstance(record, list) or not record[0] or len(record[0]) < 2:
                self.logger.warning('DB: ZoneEvents query returned no data; skipping image save')
                continue

            box = record[0][0]
            zone_coords = record[0][1]

            # Проверка на None перед отрисовкой
            if box is None or zone_coords is None:
                self.logger.warning('DB: Missing box/zone_coords in RETURNING; skipping image save')
                continue

            self._save_image(preview_path, frame_path, image, box, zone_coords)

            if query_type == 'insert':
                threading_events.notify('new event')
            elif query_type == 'update':
                threading_events.notify('update event')

    def _save_image(self, preview_path, frame_path, image, box, zone_coords):
        preview_save_dir = os.path.join(self.image_dir, preview_path)
        frame_save_dir = os.path.join(self.image_dir, frame_path)
        preview = cv2.resize(copy.deepcopy(image.image), self.preview_size, cv2.INTER_NEAREST)
        preview_boxes = utils.draw_preview_boxes_zones(preview, self.preview_width, self.preview_height, box, zone_coords)
        preview_saved = cv2.imwrite(preview_save_dir, preview_boxes)
        frame_saved = cv2.imwrite(frame_save_dir, image.image)
        if not preview_saved or not frame_saved:
            self.logger.error(f'ERROR: can\'t save image file {frame_save_dir}')

    def _prepare_for_updating(self, event):
        fields_for_updating = {'time_left': event.time_left,
                               'box_left': event.box_left,
                               'frame_path_left': self._get_img_path('frame', 'zone_left', event, time_lost=event.time_left),
                               'preview_path_left': self._get_img_path('preview', 'zone_left', event, time_lost=event.time_left)}

        image_height, image_width, _ = event.img_left.image.shape
        fields_for_updating['box_left'] = copy.deepcopy(fields_for_updating['box_left'])
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
                             'project_id': self.db_controller.get_project_id(),
                             'job_id': self.db_controller.get_job_id()}

        # Нормализуем координаты зоны, чтобы избежать ошибок сравнения float
        coords = [list(point) for point in event.zone.get_coords()]
        coords_rounded = [[round(p[0], 4), round(p[1], 4)] for p in coords]
        fields_for_saving['zone_coords'] = coords_rounded

        image_height, image_width, _ = event.img_entered.image.shape
        fields_for_saving['box_entered'] = copy.deepcopy(fields_for_saving['box_entered'])
        fields_for_saving['box_entered'][0] /= image_width
        fields_for_saving['box_entered'][1] /= image_height
        fields_for_saving['box_entered'][2] /= image_width
        fields_for_saving['box_entered'][3] /= image_height
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()),
                fields_for_saving['preview_path_entered'], fields_for_saving['frame_path_entered'])

    def _get_img_path(self, image_type, obj_event_type, event, time_stamp=None, time_lost=None):
        save_dir = self.db_params['image_dir']
        img_dir = os.path.join(save_dir, 'images')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y_%m_%d')

        current_day_path = os.path.join(img_dir, cur_date_str)
        # Unified folders for events: events_found_*/events_lost_* (frames/previews)
        tag = 'events_found' if obj_event_type == 'zone_entered' else 'events_lost'
        subdir = f"{tag}_{'previews' if image_type == 'preview' else 'frames'}"
        obj_type_path = os.path.join(current_day_path, subdir)

        if not os.path.exists(img_dir):
            os.makedirs(img_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(obj_type_path):
            os.makedirs(obj_type_path, exist_ok=True)

        zone_id = event.zone.get_zone_id()
        obj_id = event.object_id
        if obj_event_type == 'zone_entered':
            timestamp = time_stamp.strftime('%Y_%m_%d_%H_%M_%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_zone{zone_id}_obj{obj_id}_{image_type}.jpeg')
        elif obj_event_type == 'zone_left':
            timestamp = time_lost.strftime('%Y_%m_%d_%H_%M_%S_%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_zone{zone_id}_obj{obj_id}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)
