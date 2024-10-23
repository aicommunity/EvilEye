import copy
import time
from utils import event
from queue import Queue
from threading import Thread
from threading import Condition
from object_tracker.object_tracking_base import TrackingResult
from object_tracker.object_tracking_base import TrackingResultList


class ObjectResult:
    def __init__(self):
        self.object_id = 0
        self.source_id = None
        self.frame_id = None
        self.class_id = None
        self.tracks: list[TrackingResult] = []
        self.last_update = False
        self.lost_frames = 0
        self.properties = dict()  # some object features in scene (i.e. is_moving, is_immovable, immovable_time, zone_visited, zone_time_spent etc)
        self.object_data = dict()  # internal object data


class ObjectResultList:
    def __init__(self):
        self.objects: list[ObjectResult] = []

    def find_last_frame_id(self):
        frame_id = 0
        for obj in self.objects:
            if frame_id < obj.frame_id:
                frame_id = obj.frame_id

        return frame_id


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

    def put(self, objs):  # Добавление данных из детектора/трекера в очередь
        self.objs_queue.put(objs)

    def get(self, objs_type, cam_id):  # Получение списка объектов в зависимости от указанного типа
        # Блокируем остальные потоки на время получения объектов
        result = None
        with self.condition:
            if objs_type == 'new':
                result = copy.deepcopy(self.new_objs)
            elif objs_type == 'active':
                result = copy.deepcopy(self._get_active(cam_id))
            elif objs_type == 'lost':
                result = copy.deepcopy(self.lost_objs)
            else:
                raise Exception('Such type of objects does not exist')
            self.condition.notify()

        return result

    def _get_active(self, cam_id):
        source_objects = ObjectResultList()
        for obj in self.active_objs.objects:
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

            # Блокируем остальные потоки для предотвращения одновременного обращения к объектам
            with self.condition:
                self._handle_active(tracking_results)
                # self.db_controller.put('emerged', (1, [45.0, 37.0, 94.0, 273.0], 77.5, 1.0))
                # event.notify('handler update', 'emerged', self.db_controller.get_fields_names('emerged'))
                # Оповещаем остальные потоки, снимаем блокировку
                self.condition.notify()
            self.objs_queue.task_done()

    def _handle_active(self, tracking_results: TrackingResultList):
        for active_obj in self.active_objs.objects:
            active_obj.last_update = False

        for track in tracking_results.tracks:
            track_object = None
            for active_obj in self.active_objs.objects:
                if active_obj.tracks[-1].track_id == track.track_id:
                    track_object = active_obj
                    break

            if track_object:
                track_object.source_id = tracking_results.source_id
                track_object.frame_id = tracking_results.frame_id
                track_object.class_id = track.class_id
                track_object.tracks.append(track)
                print(f"object_id={track_object.object_id}, track_id={track_object.tracks[-1].track_id}, len(tracks)={len(track_object.tracks)}")
                if len(track_object.tracks) > self.history:  # Если количество данных превышает размер истории, удаляем самые старые данные об объекте
                    del track_object.tracks[0]
                track_object.last_update = True
                track_object.lost_frames = 0
            else:
                obj = ObjectResult()
                obj.source_id = tracking_results.source_id
                obj.class_id = track.class_id
                print(f'Class: {obj.class_id}')
                obj.frame_id = tracking_results.frame_id
                obj.object_id = self.object_id_counter
                self.object_id_counter += 1
                obj.tracks.append(track)
                data = self._prepare_for_saving('emerged', copy.deepcopy(obj))
                self.db_controller.put('emerged', data)
                event.notify('handler update')
                self.active_objs.objects.append(obj)

        filtered_active_objects = []
        for active_obj in self.active_objs.objects:
            if not active_obj.last_update:
                active_obj.lost_frames += 1
                if active_obj.lost_frames >= self.lost_thresh:
                    # data = self._prepare_for_saving('lost', copy.deepcopy(active_obj))
                    # self.db_controller.put('lost', data)
                    self.lost_objs.objects.append(active_obj)
                else:
                    filtered_active_objects.append(active_obj)
            else:
                filtered_active_objects.append(active_obj)
        self.active_objs.objects = filtered_active_objects

    def _prepare_for_saving(self, table_name, obj: ObjectResult) -> list:
        table_fields = self.db_controller.get_fields_names(table_name)
        fields_for_saving = []
        for field in table_fields:
            attr_value = getattr(obj, field, None)
            print(f'field: {field}, value: {attr_value}')
            if attr_value is None:
                attr_value = getattr(obj.tracks[-1], field, None)
                print(f'field: {field}, value: {attr_value}')
            if attr_value is None:
                raise Exception(f'Given object doesn\'t have required fields {field}')
            fields_for_saving.append(attr_value)
        return fields_for_saving


