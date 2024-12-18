import copy
import json
import time
import os
import datetime
import core
from capture.video_capture_base import CaptureImage
from utils import event
from utils.utils import ObjectResultEncoder
from queue import Queue
from threading import Thread
from threading import Condition
from object_tracker.object_tracking_base import TrackingResult
from object_tracker.object_tracking_base import TrackingResultList
from timeit import default_timer as timer
from .object_result import ObjectResultHistory, ObjectResult, ObjectResultList

'''
Модуль работы с объектами ожидает данные от детектора в виде dict: {'cam_id': int, 'objects': list, 'actual': bool}, 
элемент objects при этом содержит словари с данными о каждом объекте (рамка, достоверность, класс)

Данные от трекера в виде dict: {'cam_id': int, 'objects': list}, где objects тоже содержит словари с данными о каждом
объекте (айди, рамка, достоверность, класс). Эти данные затем преобразуются к виду массива словарей, где каждый словарь
соответствует конкретному объекту и содержит его историю в виде dict:
{'track_id': int, 'obj_info': list, 'lost_frames': int, 'last_update': bool}, где obj_info содержит словари,
полученные на входе (айди, рамка, достоверность, класс), которые соответствуют данному объекту.
'''


class ObjectsHandler(core.EvilEyeBase):
    def __init__(self, db_controller):
        super().__init__()
        # Очередь для потокобезопасного приема данных от каждой камеры
        self.objs_queue = Queue()
        # Списки для хранения различных типов объектов
        self.new_objs: ObjectResultList = ObjectResultList()
        self.active_objs: ObjectResultList = ObjectResultList()
        self.lost_objs: ObjectResultList = ObjectResultList()
        self.history_len = 1
        self.lost_thresh = 5  # Порог перевода (в кадрах) в потерянные объекты

        self.db_controller = db_controller
        self.db_params = self.db_controller.get_params()
        self.cameras_params = self.db_controller.get_cameras_params()
        # Условие для блокировки других потоков
        self.condition = Condition()
        # Поток, который отвечает за получение объектов из очереди и распределение их по спискам
        self.handler = Thread(target=self.handle_objs)
        self.run_flag = False
        self.object_id_counter = 1
        self.lost_store_time_secs = 10
        self.last_sources = dict()

    def default(self):
        pass

    def init_impl(self):
        pass

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        self.lost_store_time_secs = self.params.get('lost_store_time_secs', 60)
        self.history_len = self.params.get('history_len', 1)
        self.lost_thresh = self.params.get('lost_thresh', 5)

    def stop(self):
        self.run_flag = False
        self.objs_queue.put(None)
        self.handler.join()
        print('Handler stopped')

    def start(self):
        self.run_flag = True
        self.handler.start()

    def put(self, data):  # Добавление данных из детектора/трекера в очередь
        self.objs_queue.put(data)

    def get(self, objs_type, cam_id):  # Получение списка объектов в зависимости от указанного типа
        # Блокируем остальные потоки на время получения объектов
        result = None
        with self.condition:
            self.condition.acquire()
            if objs_type == 'new':
                result = copy.deepcopy(self.new_objs)
            elif objs_type == 'active':
                result = self._get_active(cam_id)
            elif objs_type == 'lost':
                result = self._get_lost(cam_id)
            elif objs_type == 'all':
                result = self._get_all(cam_id)
            else:
                raise Exception('Such type of objects does not exist')
            self.condition.release()
            self.condition.notify_all()

        return result

    def _get_active(self, cam_id):
        source_objects = ObjectResultList()
        for obj in self.active_objs.objects:
            if obj.source_id == cam_id:
                source_objects.objects.append(copy.deepcopy(obj))
        return source_objects

    def _get_lost(self, cam_id):
        source_objects = ObjectResultList()
        for obj in self.lost_objs.objects:
            if obj.source_id == cam_id:
                source_objects.objects.append(copy.deepcopy(obj))
        return source_objects

    def _get_all(self, cam_id):
        source_objects = ObjectResultList()
        for obj in self.active_objs.objects:
            if obj.source_id == cam_id:
                source_objects.objects.append(copy.deepcopy(obj))
        for obj in self.lost_objs.objects:
            if obj.source_id == cam_id:
                source_objects.objects.append(copy.deepcopy(obj))
        return source_objects

    def handle_objs(self):  # Функция, отвечающая за работу с объектами
        print('Handler running: waiting for objects...')
        while self.run_flag:
            time.sleep(0.01)
            # if self.objs_queue.empty():
            #    continue
            tracking_results = self.objs_queue.get()
            if tracking_results is None:
                continue
            tracks, image = tracking_results
            # Блокируем остальные потоки для предотвращения одновременного обращения к объектам
            with self.condition:
                self.condition.acquire()
                self._handle_active(tracks, image)
                # self.db_controller.put('emerged', (1, [45.0, 37.0, 94.0, 273.0], 77.5, 1.0))
                # event.notify('handler update', 'emerged', self.db_controller.get_fields_names('emerged'))
                # Оповещаем остальные потоки, снимаем блокировку
                self.condition.release()
                self.condition.notify_all()
            self.objs_queue.task_done()

    def _handle_active(self, tracking_results: TrackingResultList, image):
        for active_obj in self.active_objs.objects:
            active_obj.last_update = False

        for track in tracking_results.tracks:
            track_object = None
            for active_obj in self.active_objs.objects:
                if active_obj.track.track_id == track.track_id:
                    track_object = active_obj
                    break

            if track_object:
                track_object.source_id = tracking_results.source_id
                track_object.frame_id = tracking_results.frame_id
                track_object.class_id = track.class_id
                track_object.track = track
                track_object.last_image = image
                # print(f"object_id={track_object.object_id}, track_id={track_object.track.track_id}, len(history)={len(track_object.history)}")
                track_object.history.append(track_object.get_current_history_element())
                if len(track_object.history) > self.history_len:  # Если количество данных превышает размер истории, удаляем самые старые данные об объекте
                    del track_object.history[0]
                track_object.last_update = True
                track_object.lost_frames = 0
            else:
                obj = ObjectResult()
                obj.source_id = tracking_results.source_id
                obj.class_id = track.class_id
                obj.time_stamp = tracking_results.time_stamp
                obj.frame_id = tracking_results.frame_id
                obj.object_id = self.object_id_counter
                obj.last_image = image
                self.object_id_counter += 1
                obj.track = track
                obj.history.append(obj.get_current_history_element())
                height, width, _ = image.image.shape
                start_prepare_it = timer()
                fields, data, preview_path, frame_path = self._prepare_for_saving(obj, width, height)
                end_prepare_it = timer()
                start_insert_it = timer()
                self.db_controller.insert('objects', fields, data, preview_path, frame_path, image)
                end_insert_it = timer()
                # print(f'Insert time: {end_insert_it - start_insert_it}; Preparation time: {end_prepare_it-start_prepare_it}')
                self.active_objs.objects.append(obj)

        filtered_active_objects = []
        for active_obj in self.active_objs.objects:
            # print(active_obj)
            # print(f'{active_obj.source_id} == {tracking_results.source_id}')
            if not active_obj.last_update and active_obj.source_id == tracking_results.source_id:
                active_obj.lost_frames += 1
                if active_obj.lost_frames >= self.lost_thresh:
                    active_obj.time_lost = datetime.datetime.now()
                    height, width, _ = active_obj.last_image.image.shape
                    start_prepare_it = timer()
                    fields, data, preview_path, frame_path = self._prepare_for_updating(active_obj, width, height)
                    end_prepare_it = timer()
                    start_update_it = timer()
                    self.db_controller.update('objects', fields, data, active_obj.object_id,
                                              preview_path, frame_path, active_obj.last_image)
                    end_update_it = timer()
                    # print(f'Update time: {end_update_it - start_update_it}; Preparation time:{end_prepare_it-start_prepare_it}')
                    # updated_fields_data = self.db_controller.update('emerged', fields=['time_lost', "lost_preview_path",
                    #                                                                    'lost_frame_path', 'lost_bounding_box'],
                    #                                                 obj_id=active_obj.object_id,
                    #                                                 data=(active_obj.time_lost, lost_preview_path,
                    #                                                       lost_img_path, active_obj.tracks[-1].bounding_box))
                    # # print(updated_fields_data)
                    # event.notify('handler fields updated', ['time_lost', 'lost_preview_path', 'lost_frame_path'],
                    #              updated_fields_data)
                    # data = self._prepare_for_saving('lost', copy.deepcopy(active_obj))
                    # self.db_controller.put('lost', data)
                    self.lost_objs.objects.append(active_obj)
                else:
                    filtered_active_objects.append(active_obj)
            else:
                filtered_active_objects.append(active_obj)
        self.active_objs.objects = filtered_active_objects

        start_index_for_remove = None
        for i in reversed(range(len(self.lost_objs.objects))):
            if (datetime.datetime.now() - self.lost_objs.objects[i].time_lost).total_seconds() > self.lost_store_time_secs:
                start_index_for_remove = i
                break
        if start_index_for_remove:
            self.lost_objs.objects = self.lost_objs.objects[start_index_for_remove:]

    def _prepare_for_saving(self, obj: ObjectResult, image_width, image_height) -> tuple[list, list, str, str]:
        fields_for_saving = {'source_id': obj.source_id,
                             'source_name': '',
                             'time_stamp': obj.time_stamp,
                             'time_lost': obj.time_lost,
                             'object_id': obj.object_id,
                             'bounding_box': obj.track.bounding_box,
                             'lost_bounding_box': None,
                             'confidence': obj.track.confidence,
                             'class_id': obj.class_id,
                             'preview_path': self._get_img_path('preview', 'detected', obj),
                             'lost_preview_path': None,
                             'frame_path': self._get_img_path('frame', 'detected', obj),
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

        fields_for_saving['bounding_box'] = copy.deepcopy(fields_for_saving['bounding_box'])
        fields_for_saving['bounding_box'][0] /= image_width
        fields_for_saving['bounding_box'][1] /= image_height
        fields_for_saving['bounding_box'][2] /= image_width
        fields_for_saving['bounding_box'][3] /= image_height
        return (list(fields_for_saving.keys()), list(fields_for_saving.values()),
                fields_for_saving['preview_path'], fields_for_saving['frame_path'])

    def _prepare_for_updating(self, obj: ObjectResult, image_width, image_height):
        fields_for_updating = {'lost_bounding_box': obj.track.bounding_box,
                               'time_lost': obj.time_lost,
                               'lost_preview_path': self._get_img_path('preview', 'lost', obj),
                               'lost_frame_path': self._get_img_path('frame', 'lost', obj),
                               'object_data': json.dumps(obj.__dict__, cls=ObjectResultEncoder)}

        fields_for_updating['lost_bounding_box'] = copy.deepcopy(fields_for_updating['lost_bounding_box'])
        fields_for_updating['lost_bounding_box'][0] /= image_width
        fields_for_updating['lost_bounding_box'][1] /= image_height
        fields_for_updating['lost_bounding_box'][2] /= image_width
        fields_for_updating['lost_bounding_box'][3] /= image_height
        return (list(fields_for_updating.keys()), list(fields_for_updating.values()),
                fields_for_updating['lost_preview_path'], fields_for_updating['lost_frame_path'])

    def _get_img_path(self, image_type, obj_event_type, obj):
        save_dir = self.db_params['image_dir']
        img_dir = os.path.join(save_dir, 'images')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y_%m_%d')

        current_day_path = os.path.join(img_dir, cur_date_str)
        obj_type_path = os.path.join(current_day_path, obj_event_type + '_' + image_type + 's')
        # obj_event_path = os.path.join(current_day_path, obj_event_type)
        if not os.path.exists(img_dir):
            os.mkdir(img_dir)
        if not os.path.exists(current_day_path):
            os.mkdir(current_day_path)
        if not os.path.exists(obj_type_path):
            os.mkdir(obj_type_path)
        # if not os.path.exists(obj_event_path):
        #     os.mkdir(obj_event_path)

        if obj_event_type == 'detected':
            timestamp = obj.time_stamp.strftime('%Y_%m_%d_%H_%M_%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{image_type}.jpeg')
        elif obj_event_type == 'lost':
            timestamp = obj.time_lost.strftime('%Y_%m_%d_%H_%M_%S_%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)
