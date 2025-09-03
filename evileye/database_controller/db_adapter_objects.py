import time

from .database_controller_pg import DatabaseControllerPg
from .db_adapter import DatabaseAdapterBase
import json
from ..utils.utils import ObjectResultEncoder
import copy
import datetime
import os
from timeit import default_timer as timer
import cv2
from ..utils import threading_events
from ..utils import utils
from psycopg2 import sql


class DatabaseAdapterObjects(DatabaseAdapterBase):
    def __init__(self, db_controller):
        super().__init__(db_controller)
        self.image_dir = self.db_params['image_dir']
        self.preview_width = self.db_params['preview_width']
        self.preview_height = self.db_params['preview_height']
        self.preview_size = (self.preview_width, self.preview_height)

    def _insert_impl(self, obj):
        fields, data, preview_path, frame_path = self._prepare_for_saving(obj)
        query_type = 'insert'
        insert_query = sql.SQL("INSERT INTO {} ({}) VALUES ({}) RETURNING record_id, bounding_box").format(
            sql.Identifier('objects'),
            sql.SQL(",").join(map(sql.Identifier, fields)),
            sql.SQL(', ').join(sql.Placeholder() * len(fields))
        )
        self.queue_in.put((query_type, insert_query, data, preview_path, frame_path, obj.last_image))

    def _update_impl(self, obj):
        fields, data, preview_path, frame_path = self._prepare_for_updating(obj)

        query_type = 'Update'
        data = list(data)
        data.append(obj.object_id)
        data = tuple(data)
        table_name = 'objects'
        last_obj_query = sql.SQL('''SELECT distinct on (object_id) record_id FROM {table} WHERE object_id = {id} 
                                    ORDER BY object_id, record_id DESC''').format(
            id=sql.Placeholder(),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)),
            table=sql.Identifier(table_name))
        update_query = sql.SQL('UPDATE {table} SET {data} WHERE record_id=({selected}) '
                               'RETURNING record_id, lost_bounding_box').format(
            table=sql.Identifier(table_name),
            data=sql.SQL(', ').join(
                sql.Composed([sql.Identifier(field), sql.SQL(" = "), sql.Placeholder()]) for field in fields),
            selected=sql.Composed(last_obj_query),
            fields=sql.SQL(",").join(map(sql.Identifier, fields)))
        self.queue_in.put((query_type, update_query, data, preview_path, frame_path, obj.last_image))

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

            record = self.db_controller.query(query_string, data)
            row_num = record[0][0]
            box = record[0][1]
            start_save_it = timer()
            self._save_image(preview_path, frame_path, image, box)
            end_save_it = timer()
            if query_type == 'insert':
                threading_events.notify('handler new object')
            elif query_type == 'update':
                threading_events.notify('handler update object')

    def _save_image(self, preview_path, frame_path, image, box):
        preview_save_dir = os.path.join(self.image_dir, preview_path)
        frame_save_dir = os.path.join(self.image_dir, frame_path)
        preview = cv2.resize(copy.deepcopy(image.image), self.preview_size, cv2.INTER_NEAREST)
        preview_boxes = utils.draw_preview_boxes(preview, self.preview_width, self.preview_height, box)
        preview_saved = cv2.imwrite(preview_save_dir, preview_boxes)
        frame_saved = cv2.imwrite(frame_save_dir, image.image)
        if not preview_saved or not frame_saved:
            print(f'ERROR: can\'t save image file {frame_save_dir}')

    def _prepare_for_updating(self, obj):
        fields_for_updating = {'lost_bounding_box': obj.track.bounding_box,
                               'time_lost': obj.time_lost,
                               'lost_preview_path': '',
                               'lost_frame_path': '',
                               'object_data': json.dumps(obj.__dict__, cls=ObjectResultEncoder)}

        src_name = ''
        for camera in self.cameras_params:
            if obj.source_id in camera['source_ids']:
                id_idx = camera['source_ids'].index(obj.source_id)
                src_name = camera['source_names'][id_idx]
                break
        fields_for_updating['lost_preview_path'] = self._get_img_path('preview', 'lost',
                                                                      src_name, obj)
        fields_for_updating['lost_frame_path'] = self._get_img_path('frame', 'lost',
                                                                    src_name, obj)

        image_height, image_width, _ = obj.last_image.image.shape
        fields_for_updating['lost_bounding_box'] = copy.deepcopy(fields_for_updating['lost_bounding_box'])
        fields_for_updating['lost_bounding_box'][0] /= image_width
        fields_for_updating['lost_bounding_box'][1] /= image_height
        fields_for_updating['lost_bounding_box'][2] /= image_width
        fields_for_updating['lost_bounding_box'][3] /= image_height
        return (list(fields_for_updating.keys()), list(fields_for_updating.values()),
                fields_for_updating['lost_preview_path'], fields_for_updating['lost_frame_path'])

    def _prepare_for_saving(self, obj) -> tuple[list, list, str, str]:
        fields_for_saving = {'source_id': obj.source_id,
                             'source_name': '',
                             'time_stamp': obj.time_detected,
                             'time_lost': obj.time_lost,
                             'object_id': obj.object_id,
                             'bounding_box': obj.track.bounding_box,
                             'lost_bounding_box': None,
                             'confidence': obj.track.confidence,
                             'class_id': obj.class_id,
                             'preview_path': '',
                             'lost_preview_path': None,
                             'frame_path': '',
                             'lost_frame_path': None,
                             'object_data': json.dumps(obj.__dict__, cls=ObjectResultEncoder),
                             'project_id': self.db_controller.get_project_id(),
                             'job_id': self.db_controller.get_job_id(),
                             'camera_full_address': ''}

        for camera in self.cameras_params:
            if obj.source_id in camera['source_ids']:
                id_idx = camera['source_ids'].index(obj.source_id)
                fields_for_saving['source_name'] = camera['source_names'][id_idx]
                fields_for_saving['camera_full_address'] = camera['camera']
                break
        fields_for_saving['preview_path'] = self._get_img_path('preview', 'detected',
                                                               fields_for_saving['source_name'], obj)
        fields_for_saving['frame_path'] = self._get_img_path('frame', 'detected',
                                                             fields_for_saving['source_name'], obj)

        image_height, image_width, _ = obj.last_image.image.shape
        fields_for_saving['bounding_box'] = copy.deepcopy(fields_for_saving['bounding_box'])
        fields_for_saving['bounding_box'][0] /= image_width
        fields_for_saving['bounding_box'][1] /= image_height
        fields_for_saving['bounding_box'][2] /= image_width
        fields_for_saving['bounding_box'][3] /= image_height
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()),
                fields_for_saving['preview_path'], fields_for_saving['frame_path'])

    def _get_img_path(self, image_type, obj_event_type, src_name, obj):
        save_dir = self.db_params['image_dir']
        img_dir = os.path.join(save_dir, 'images')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y_%m_%d')

        current_day_path = os.path.join(img_dir, cur_date_str)
        obj_type_path = os.path.join(current_day_path, obj_event_type + '_' + image_type + 's')
        # obj_event_path = os.path.join(current_day_path, obj_event_type)
        os.makedirs(img_dir, exist_ok=True)
        os.makedirs(current_day_path, exist_ok=True)
        os.makedirs(obj_type_path, exist_ok=True)
        # if not os.path.exists(obj_event_path):
        #     os.mkdir(obj_event_path)

        if obj_event_type == 'detected':
            timestamp = obj.time_detected.strftime('%Y_%m_%d_%H_%M_%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{src_name}_{image_type}.jpeg')
        elif obj_event_type == 'lost':
            timestamp = obj.time_lost.strftime('%Y_%m_%d_%H_%M_%S_%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{src_name}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)
