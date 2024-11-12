import copy
import time
import os
import cv2
import datetime

import objects_handler.objects_handler
from capture.video_capture_base import CaptureImage
from utils import event
from utils import utils
from queue import Queue
from threading import Thread
from threading import Condition
from object_tracker.object_tracking_base import TrackingResult
from object_tracker.object_tracking_base import TrackingResultList
from timeit import default_timer as timer


class ObjectResultHistory:
    def __init__(self):
        self.object_id = 0
        self.source_id = None
        self.frame_id = None
        self.class_id = None
        self.time_lost = None
        self.time_stamp = None
        self.last_update = False
        self.last_image = None
        self.lost_frames = 0
        self.track = None
        self.properties = dict()  # some object features in scene (i.e. is_moving, is_immovable, immovable_time, zone_visited, zone_time_spent etc)
        self.object_data = dict()  # internal object data


class ObjectResult(ObjectResultHistory):
    def __init__(self):
        super().__init__()
        self.history: list[ObjectResultHistory] = []

    def __str__(self):
        return f'ID: {self.object_id}, Source: {self.source_id}, Updated: {self.last_update}, Lost: {self.lost_frames}'

    def get_current_history_element(self):
        result = ObjectResultHistory()
        result.object_id = self.object_id
        result.source_id = self.source_id
        result.frame_id = self.frame_id
        result.class_id = self.class_id
        result.time_lost = self.time_lost
        result.time_stamp = self.time_stamp
        result.last_update = self.last_update
        result.last_image = self.last_image
        result.lost_frames = self.lost_frames
        result.track = self.track
        result.properties = self.properties
        result.object_data = self.object_data
        return result


class ObjectResultList:
    def __init__(self):
        self.objects: list[ObjectResult] = []

    def find_last_frame_id(self):
        frame_id = 0
        for obj in self.objects:
            if frame_id < obj.frame_id:
                frame_id = obj.frame_id

        return frame_id

    def find_objects_by_frame_id(self, frame_id, use_history: bool):
        objs = []
        if frame_id is None:
            return self.objects

        for obj in self.objects:
            if frame_id == obj.frame_id:
                objs.append(obj)
            elif obj.history and use_history:
                for hist in obj.history:
                    if hist.frame_id == frame_id:
                        objs.append(obj)
                        break

        return objs

    def get_num_objects(self):
        return len(self.objects)


'''
Модуль работы с объектами ожидает данные от детектора в виде dict: {'cam_id': int, 'objects': list, 'actual': bool}, 
элемент objects при этом содержит словари с данными о каждом объекте (рамка, достоверность, класс)

Данные от трекера в виде dict: {'cam_id': int, 'objects': list}, где objects тоже содержит словари с данными о каждом
объекте (айди, рамка, достоверность, класс). Эти данные затем преобразуются к виду массива словарей, где каждый словарь
соответствует конкретному объекту и содержит его историю в виде dict:
{'track_id': int, 'obj_info': list, 'lost_frames': int, 'last_update': bool}, где obj_info содержит словари,
полученные на входе (айди, рамка, достоверность, класс), которые соответствуют данному объекту.
'''


class ObjectsHandler:
    def __init__(self, db_controller, history_len=1, lost_thresh=5):
        # Очередь для потокобезопасного приема данных от каждой камеры
        self.objs_queue = Queue()
        # Списки для хранения различных типов объектов
        self.new_objs: ObjectResultList = ObjectResultList()
        self.active_objs: ObjectResultList = ObjectResultList()
        self.lost_objs: ObjectResultList = ObjectResultList()
        self.history = history_len
        self.lost_thresh = lost_thresh  # Порог перевода (в кадрах) в потерянные объекты

        self.db_controller = db_controller
        self.db_params = self.db_controller.get_params()
        # Условие для блокировки других потоков
        self.condition = Condition()
        # Поток, который отвечает за получение объектов из очереди и распределение их по спискам
        self.handler = Thread(target=self.handle_objs)
        self.run_flag = False
        self.object_id_counter = 1
        self.last_sources = dict()

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
                #track_object.last_image = image
                # print(f"object_id={track_object.object_id}, track_id={track_object.track.track_id}, len(history)={len(track_object.history)}")
                track_object.history.append(track_object.get_current_history_element())
                if len(track_object.history) > self.history:  # Если количество данных превышает размер истории, удаляем самые старые данные об объекте
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
                #obj.last_image = image
                self.object_id_counter += 1
                obj.track = track
                obj.history.append(obj.get_current_history_element())
                data, preview_path, frame_path = self._prepare_for_saving('emerged', obj)
                self.db_controller.insert('emerged', data, preview_path, frame_path, image)
                self.active_objs.objects.append(obj)

        filtered_active_objects = []
        for active_obj in self.active_objs.objects:
            # print(active_obj)
            # print(f'{active_obj.source_id} == {tracking_results.source_id}')
            if not active_obj.last_update and active_obj.source_id == tracking_results.source_id:
                active_obj.lost_frames += 1
                if active_obj.lost_frames >= self.lost_thresh:
                    # active_obj.time_lost = datetime.datetime.now()
                    # lost_preview_path = self._save_image('preview', 'lost', active_obj.last_image, active_obj)
                    # lost_img_path = self._save_image('frame', 'lost', active_obj.last_image, active_obj)
                    # # data = self._prepare_for_saving('emerged', copy.deepcopy(active_obj), image)
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

    def _prepare_for_saving(self, table_name, obj: ObjectResult) -> tuple[list, str, str]:
        table_fields = self.db_controller.get_fields_names(table_name)
        fields_for_saving = []
        preview_path = None
        frame_path = None

        if table_fields is None:
            return fields_for_saving, preview_path, frame_path

        for field in table_fields:
            if field == 'preview_path':
                preview_path = self._get_img_path('preview', 'emerged', obj)
                fields_for_saving.append(preview_path)
                continue
            if field == 'frame_path':
                frame_path = self._get_img_path('frame', 'emerged', obj)
                fields_for_saving.append(frame_path)
                continue
            attr_value = getattr(obj, field, None)
            print(f'field: {field}, value: {attr_value}')
            if attr_value is None:
                attr_value = getattr(obj.track, field, None)
                print(f'field: {field}, value: {attr_value}')
            if attr_value is None and not self.db_controller.has_default(table_name, field):
                raise Exception(f'Given object doesn\'t have required fields {field}')
            fields_for_saving.append(attr_value)
        return fields_for_saving, preview_path, frame_path

    def _get_img_path(self, image_type, obj_event_type, obj):
        save_dir = self.db_params['image_dir']
        img_dir = os.path.join(save_dir, 'images')
        image_type_path = os.path.join(img_dir, image_type + 's')
        obj_event_path = os.path.join(image_type_path, obj_event_type)
        if not os.path.exists(img_dir):
            os.mkdir(img_dir)
        if not os.path.exists(image_type_path):
            os.mkdir(image_type_path)
        if not os.path.exists(obj_event_path):
            os.mkdir(obj_event_path)

        if obj_event_type == 'emerged':
            timestamp = obj.time_stamp.strftime('%d_%m_%Y_%H_%M_%S_%f')
            img_path = os.path.join(obj_event_path, f'{image_type}_at_{timestamp}.jpeg')
        elif obj_event_type == 'lost':
            timestamp = obj.time_lost.strftime('%d_%m_%Y_%H_%M_%S_%f')
            img_path = os.path.join(obj_event_path, f'{image_type}_at_{timestamp}.jpeg')
        return os.path.relpath(img_path, save_dir)
