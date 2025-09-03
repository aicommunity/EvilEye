import copy
import json
import time
import os
import datetime
import copy
from ..core.base_class import EvilEyeBase
from ..capture.video_capture_base import CaptureImage
from ..utils import threading_events
from ..utils.utils import ObjectResultEncoder
from queue import Queue
from threading import Thread
from threading import Condition, Lock
from ..object_tracker.tracking_results import TrackingResult
from ..object_tracker.tracking_results import TrackingResultList
from timeit import default_timer as timer
from .object_result import ObjectResultHistory, ObjectResult, ObjectResultList
from ..database_controller.db_adapter_objects import DatabaseAdapterObjects
from .labeling_manager import LabelingManager
from pympler import asizeof
import cv2
from ..utils import utils

'''
Модуль работы с объектами ожидает данные от детектора в виде dict: {'cam_id': int, 'objects': list, 'actual': bool}, 
элемент objects при этом содержит словари с данными о каждом объекте (рамка, достоверность, класс)

Данные от трекера в виде dict: {'cam_id': int, 'objects': list}, где objects тоже содержит словари с данными о каждом
объекте (айди, рамка, достоверность, класс). Эти данные затем преобразуются к виду массива словарей, где каждый словарь
соответствует конкретному объекту и содержит его историю в виде dict:
{'track_id': int, 'obj_info': list, 'lost_frames': int, 'last_update': bool}, где obj_info содержит словари,
полученные на входе (айди, рамка, достоверность, класс), которые соответствуют данному объекту.
'''


class ObjectsHandler(EvilEyeBase):
    def __init__(self, db_controller, db_adapter):
        super().__init__()
        # Очередь для потокобезопасного приема данных от каждой камеры
        self.objs_queue = Queue()
        # Списки для хранения различных типов объектов
        self.new_objs: ObjectResultList = ObjectResultList()
        self.active_objs: ObjectResultList = ObjectResultList()
        self.lost_objs: ObjectResultList = ObjectResultList()
        self.history_len = 30
        self.lost_thresh = 5  # Порог перевода (в кадрах) в потерянные объекты
        self.max_active_objects = 100
        self.max_lost_objects = 100

        self.db_controller = db_controller
        self.db_adapter = db_adapter
        # Initialize database parameters only if database controller is available
        if self.db_controller is not None:
            self.db_params = self.db_controller.get_params()
            self.cameras_params = self.db_controller.get_cameras_params()
        else:
            self.db_params = {}
            self.cameras_params = {}
        # Условие для блокировки других потоков
        self.condition = Condition()
        self.lock = Lock()
        # Поток, который отвечает за получение объектов из очереди и распределение их по спискам
        self.handler = Thread(target=self.handle_objs)
        self.run_flag = False
        self.object_id_counter = 1
        self.lost_store_time_secs = 10
        self.last_sources = dict()

        self.snapshot = None
        self.subscribers = []
        # self.objects_file = open('roi_detector_exp_file3.txt', 'w')
        
        # Initialize labeling manager
        base_dir = self.db_params.get('image_dir', 'EvilEyeData') if self.db_params else 'EvilEyeData'
        self.labeling_manager = LabelingManager(base_dir=base_dir, cameras_params=self.cameras_params)
        
        # Initialize object_id counter from existing data
        self._init_object_id_counter()

    def _init_object_id_counter(self):
        """Initialize object_id counter from existing data to avoid ID conflicts."""
        try:
            # Get the maximum object_id from existing data
            max_existing_id = self.labeling_manager._preload_existing_data()
            
            if max_existing_id > 0:
                # Set counter to next available ID
                self.object_id_counter = max_existing_id + 1
                print(f"🔄 Initialized object_id counter to {self.object_id_counter} (max existing: {max_existing_id})")
            else:
                # No existing objects, start from 1
                self.object_id_counter = 1
                print(f"🔄 Starting with fresh object_id counter: {self.object_id_counter}")
                
        except Exception as e:
            print(f"⚠️ Warning: Error initializing object_id counter: {e}")
            print(f"ℹ️ Starting with default counter value: {self.object_id_counter}")
            # Keep default value (1)

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
        self.max_active_objects = self.params.get('max_active_objects', 100)
        self.max_lost_objects = self.params.get('max_lost_objects', 100)

    def get_params_impl(self):
        params = dict()
        params['lost_store_time_secs'] = self.lost_store_time_secs
        params['history_len'] = self.history_len
        params['lost_thresh'] = self.lost_thresh
        params['max_active_objects'] = self.max_active_objects
        params['max_lost_objects'] = self.max_lost_objects

    def stop(self):
        # self.objects_file.close()
        self.run_flag = False
        self.objs_queue.put(None)
        if self.handler.is_alive():
            self.handler.join()
        
        # Stop labeling manager and save any remaining data
        if hasattr(self, 'labeling_manager'):
            self.labeling_manager.stop()
        
        print('Handler stopped')

    def start(self):
        self.run_flag = True
        self.handler.start()

    def put(self, data):  # Добавление данных из детектора/трекера в очередь
        self.objs_queue.put(data)

    def get(self, objs_type, cam_id):  # Получение списка объектов в зависимости от указанного типа
        # Блокируем остальные потоки на время получения объектов
        result = None
        if objs_type == 'new':
            with self.lock:
                result = self.new_objs
        elif objs_type == 'active':
            result = self._get_active(cam_id)
        elif objs_type == 'lost':
            result = self._get_lost(cam_id)
        elif objs_type == 'all':
            result = self._get_all(cam_id)
        else:
            raise Exception('Such type of objects does not exist')
            # self.condition.release()
            # self.condition.notify_all()

        return result

    def subscribe(self, *subscribers):
        self.subscribers = list(subscribers)

    def _get_active(self, cam_id):
        source_objects = ObjectResultList()
        if self.snapshot is None:
            return source_objects
        for obj in self.snapshot:
            if obj.source_id == cam_id:
                source_objects.objects.append(obj)
        return source_objects

    def _get_lost(self, cam_id):
        with self.lock:
            source_objects = ObjectResultList()
            for obj in self.lost_objs.objects:
                if obj.source_id == cam_id:
                    source_objects.objects.append(obj)
        return source_objects

    def _get_all(self, cam_id):
        with self.lock:
            source_objects = ObjectResultList()
            for obj in self.active_objs.objects:
                if obj.source_id == cam_id:
                    source_objects.objects.append(obj)
            for obj in self.lost_objs.objects:
                if obj.source_id == cam_id:
                    source_objects.objects.append(obj)
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
            with self.lock:
                # self.condition.acquire()
                self._handle_active(tracks, image)
                if self.active_objs.objects:
                    self.snapshot = self.active_objs.objects
                else:
                    self.snapshot = None

            for subscriber in self.subscribers:
                subscriber.update()

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
                track_object.time_stamp = tracking_results.time_stamp
                track_object.last_image = image
                track_object.cur_video_pos = image.current_video_position
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
                obj.time_detected = tracking_results.time_stamp
                obj.frame_id = tracking_results.frame_id
                obj.object_id = self.object_id_counter
                obj.global_id = track.tracking_data.get('global_id', None)
                obj.last_image = image
                obj.cur_video_pos = image.current_video_position
                self.object_id_counter += 1
                obj.track = track
                obj.history.append(obj.get_current_history_element())
                start_insert_it = timer()
                if self.db_adapter is not None:
                    self.db_adapter.insert(obj)
                end_insert_it = timer()
                
                # Save images for found object
                self._save_object_images(obj, 'detected')
                
                # Save labeling data for found object
                try:
                    # Get full image path and extract filename with camera name
                    full_img_path = self._get_img_path('frame', 'detected', obj)
                    image_filename = os.path.basename(full_img_path)
                    preview_filename = os.path.basename(self._get_img_path('preview', 'detected', obj))
                    
                    # Get image dimensions from the image object
                    image_width = obj.last_image.width if hasattr(obj.last_image, 'width') else 1920
                    image_height = obj.last_image.height if hasattr(obj.last_image, 'height') else 1080
                    
                    object_data = self.labeling_manager.create_found_object_data(
                        obj, image_width, image_height, image_filename, preview_filename
                    )
                    self.labeling_manager.add_object_found(object_data)
                except Exception as e:
                    print(f"Error saving labeling data for found object: {e}")
                
                self.active_objs.objects.append(obj)
               # print(f"active_objs len={len(self.active_objs.objects)} size={asizeof.asizeof(self.active_objs.objects)/(1024.0*1024.0)}")
               # print(f"lost_objs len={len(self.lost_objs.objects)} size={asizeof.asizeof(self.lost_objs.objects)/(1024.0*1024.0)}")

        filtered_active_objects = []
        for active_obj in self.active_objs.objects:
            if not active_obj.last_update and active_obj.source_id == tracking_results.source_id:
                active_obj.lost_frames += 1
                if active_obj.lost_frames >= self.lost_thresh:
                    active_obj.time_lost = datetime.datetime.now()
                    start_update_it = timer()
                    if self.db_adapter is not None:
                        self.db_adapter.update(active_obj)
                    end_update_it = timer()
                    
                    # Save images for lost object
                    self._save_object_images(active_obj, 'lost')
                    
                    # Save labeling data for lost object
                    try:
                        # Get full image path and extract filename with camera name
                        full_img_path = self._get_img_path('frame', 'lost', active_obj)
                        image_filename = os.path.basename(full_img_path)
                        preview_filename = os.path.basename(self._get_img_path('preview', 'lost', active_obj))
                        
                        # Get image dimensions from the image object
                        image_width = active_obj.last_image.width if hasattr(active_obj.last_image, 'width') else 1920
                        image_height = active_obj.last_image.height if hasattr(active_obj.last_image, 'height') else 1080
                        
                        object_data = self.labeling_manager.create_lost_object_data(
                            active_obj, image_width, image_height, image_filename, preview_filename
                        )
                        self.labeling_manager.add_object_lost(object_data)
                    except Exception as e:
                        print(f"Error saving labeling data for lost object: {e}")
                    
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
        if start_index_for_remove is not None:
            self.lost_objs.objects = self.lost_objs.objects[start_index_for_remove:]

        if len(self.active_objs.objects) > self.max_active_objects:
            self.active_objs.objects = self.active_objs.objects[-self.max_active_objects:]
        if len(self.lost_objs.objects) > self.max_lost_objects:
            self.lost_objs.objects = self.lost_objs.objects[-self.max_lost_objects:]

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
                             'project_id': self.db_controller.get_project_id() if self.db_controller is not None else 0,
                             'job_id': self.db_controller.get_job_id() if self.db_controller is not None else 0,
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

    def _save_object_images(self, obj, event_type):
        """Save both preview and frame images for an object"""
        try:
            if obj.last_image is None:
                return
                
            # Save preview image
            self._save_image(obj.last_image, obj.track.bounding_box, 'preview', event_type, obj)
            
            # Save frame image
            self._save_image(obj.last_image, obj.track.bounding_box, 'frame', event_type, obj)
            
        except Exception as e:
            print(f"Error saving object images: {e}")

    def _save_image(self, image, box, image_type, obj_event_type, obj):
        """Save image to file system independent of database - using same logic as database journal"""
        try:
            # Get image path
            img_path = self._get_img_path(image_type, obj_event_type, obj)
            
            # Resolve full path
            if 'image_dir' in self.db_params and self.db_params['image_dir']:
                save_dir = self.db_params['image_dir']
            else:
                save_dir = 'EvilEyeData'  # Default directory
                
            if not os.path.isabs(save_dir):
                save_dir = os.path.join(os.getcwd(), save_dir)
            
            full_img_path = os.path.join(save_dir, img_path)
            
            # Create directory if it doesn't exist
            os.makedirs(os.path.dirname(full_img_path), exist_ok=True)
            
            # Save image using the same logic as database journal
            if image_type == 'preview':
                # Create preview with bounding box (same as database journal)
                preview = cv2.resize(copy.deepcopy(image.image), (self.db_params.get('preview_width', 300), self.db_params.get('preview_height', 150)), cv2.INTER_NEAREST)
                
                # Convert bounding box to normalized coordinates (same as database journal)
                image_height, image_width, _ = image.image.shape
                normalized_box = [
                    box[0] / image_width,   # x
                    box[1] / image_height,  # y
                    box[2] / image_width,   # width
                    box[3] / image_height   # height
                ]
                
                preview_boxes = utils.draw_preview_boxes(preview, self.db_params.get('preview_width', 300), self.db_params.get('preview_height', 150), normalized_box)
                saved = cv2.imwrite(full_img_path, preview_boxes)
            else:
                # Save original frame without any graphical info (same as database journal)
                saved = cv2.imwrite(full_img_path, image.image)
            
            if not saved:
                print(f'ERROR: can\'t save image file {full_img_path}')

        except Exception as e:
            print(f"Error saving image: {e}")

    def _get_img_path(self, image_type, obj_event_type, obj):
        # Use default image directory if database is not available
        if 'image_dir' in self.db_params and self.db_params['image_dir']:
            save_dir = self.db_params['image_dir']
        else:
            save_dir = 'EvilEyeData'  # Default directory
        img_dir = os.path.join(save_dir, 'images')
        cur_date = datetime.date.today()
        cur_date_str = cur_date.strftime('%Y_%m_%d')

        current_day_path = os.path.join(img_dir, cur_date_str)
        obj_type_path = os.path.join(current_day_path, obj_event_type + '_' + image_type + 's')
        # obj_event_path = os.path.join(current_day_path, obj_event_type)
        if not os.path.exists(img_dir):
            os.makedirs(img_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(obj_type_path):
            os.makedirs(obj_type_path, exist_ok=True)
        # if not os.path.exists(obj_event_path):
        #     os.mkdir(obj_event_path)

        # Get source name for the object
        source_name = ''
        for camera in self.cameras_params:
            if obj.source_id in camera['source_ids']:
                id_idx = camera['source_ids'].index(obj.source_id)
                source_name = camera['source_names'][id_idx]
                break
        
        if obj_event_type == 'detected':
            timestamp = obj.time_stamp.strftime('%Y_%m_%d_%H_%M_%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{source_name}_{image_type}.jpeg')
        elif obj_event_type == 'lost':
            timestamp = obj.time_lost.strftime('%Y_%m_%d_%H_%M_%S_%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{source_name}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)
