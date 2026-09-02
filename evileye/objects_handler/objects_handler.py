import copy
import json
import time
import os
import datetime
import cv2
from typing import TYPE_CHECKING, Optional, Union
from ..core.base_class import EvilEyeBase
from ..core.interfaces import IObjectHandler, IDatabaseAdapter
from ..capture.video_capture_base import CaptureImage
from ..utils import threading_events
from ..utils.utils import ObjectResultEncoder
from queue import Queue
from threading import Thread
from threading import Condition, Lock
from ..object_tracker.tracking_results import TrackingResult
from ..object_tracker.tracking_results import TrackingResultList
from ..object_detector.object_detection_base import DetectionResultList
from timeit import default_timer as timer
from .object_result import ObjectResultHistory, ObjectResult, ObjectResultList
from .labeling_manager import LabelingManager
from ..core.object_pool import ObjectPool
from ..core.tracking_dto import ensure_tracking_result_list
from pympler import asizeof
from ..database_controller.image_storage_service import ImageStorageService
from .attribute_manager import AttributeManager
import os

if TYPE_CHECKING:
    # Импорт только для type checking, чтобы избежать циклических зависимостей
    from ..database_controller.db_adapter_objects import DatabaseAdapterObjects

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
    def __init__(self, db_controller, db_adapter: Optional[IDatabaseAdapter] = None):
        super().__init__()
        # Очередь для потокобезопасного приема данных от каждой камеры
        # Важно: очередь должна быть ограниченной, иначе при высокой нагрузке
        # (много источников/детекторы/трекеры) она начинает неограниченно расти и "утекать" память.
        # Нам не нужна полная история: для GUI/событий важнее самые свежие данные.
        self.objs_queue_maxsize = 200
        self.objs_queue = Queue(maxsize=self.objs_queue_maxsize)
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
        self._last_frame_ts = {}  # Initialize timestamp tracking for attributes
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

        # Attributes aggregation (lazy-configurable)
        self.attr_manager: AttributeManager | None = None
        self._attr_conf_thresholds = {}
        self._attr_time_thresholds = {}
        self._attr_ema_alpha = 0.6

        # Инъекции/настройки от Controller (явная инициализация вместо hasattr)
        self.class_manager = None
        self.class_mapping: dict = {}

        # Object pools для переиспользования объектов (оптимизация памяти)
        self._object_result_pool: Optional[ObjectPool[ObjectResult]] = None
        self._object_history_pool: Optional[ObjectPool[ObjectResultHistory]] = None
        self._use_object_pool = True  # Можно отключить через параметры

        # Perf diagnostics (disabled by default). Enable with env EVILEYE_PERF_DIAG=1
        self._perf_diag_env = os.getenv("EVILEYE_PERF_DIAG", "").strip().lower() in {"1", "true", "yes", "on"}
        self._perf_diag_every = int(os.getenv("EVILEYE_PERF_DIAG_EVERY", "60") or "60")
        self._perf_diag_counter = 0
        self._diag_track_id_changes = 0
        self._diag_missing_track_object = 0
        self._diag_prev_track_ids_by_source: dict[int, set[int]] = {}

        # IO throttling for saving images/labeling data to avoid backlog and freezes under load
        self.save_object_images = True
        self.save_labeling_data = True
        self.save_min_interval_sec = 0.2  # per source; 0 disables throttling
        self._last_save_ts_by_source: dict[int, float] = {}
        self._last_frame_ts_by_source: dict[int, float] = {}
        self.source_stale_sec = 30.0
        self._last_stale_check_ts = 0.0

    def _init_object_id_counter(self):
        """Initialize object_id counter from existing data to avoid ID conflicts."""
        try:
            # Get the maximum object_id from existing data
            preload_fn = getattr(self.labeling_manager, "_preload_existing_data", None)
            if not callable(preload_fn):
                self.object_id_counter = 1
                self.logger.debug("LabelingManager preload is unavailable; starting object_id from 1")
                return
            max_existing_id = preload_fn()

            if max_existing_id > 0:
                # Set counter to next available ID
                self.object_id_counter = max_existing_id + 1
                self.logger.info(
                    f"Object ID counter initialized to {self.object_id_counter} (maximum existing: {max_existing_id})")
            else:
                # No existing objects, start from 1
                self.object_id_counter = 1
                self.logger.info(f"Starting with new counter object_id: {self.object_id_counter}")

        except Exception as e:
            self.logger.warning(f"Warning: Object ID counter initialization error: {e}")
            self.logger.info(f"Starting with default counter value: {self.object_id_counter}")
            # Keep default value (1)

    def _init_object_pools(self, pool_size: int = 20) -> None:
        """Инициализировать пулы объектов для переиспользования.
        
        Args:
            pool_size: Размер пула для каждого типа объектов
        """

        def reset_object_result(obj: ObjectResult) -> None:
            """Сбросить состояние ObjectResult перед переиспользованием."""
            obj.object_id = 0
            obj.global_id = None
            obj.source_id = None
            obj.frame_id = None
            obj.class_id = None
            obj.time_lost = None
            obj.time_stamp = None
            obj.time_detected = None
            obj.last_update = False
            obj.cur_video_position = None
            obj.lost_frames = 0
            obj.track = None
            obj.properties.clear()
            obj.object_data.clear()
            obj.history.clear()
            obj.attributes.clear()
            obj.last_image = None

        def reset_object_history(obj: ObjectResultHistory) -> None:
            """Сбросить состояние ObjectResultHistory перед переиспользованием."""
            obj.object_id = 0
            obj.global_id = None
            obj.source_id = None
            obj.frame_id = None
            obj.class_id = None
            obj.time_lost = None
            obj.time_stamp = None
            obj.time_detected = None
            obj.last_update = False
            obj.cur_video_position = None
            obj.lost_frames = 0
            obj.track = None
            obj.properties.clear()
            obj.object_data.clear()

        self._object_result_pool = ObjectPool(
            factory=ObjectResult,
            max_size=pool_size,
            reset_func=reset_object_result
        )
        self._object_history_pool = ObjectPool(
            factory=ObjectResultHistory,
            max_size=pool_size * 2,  # History элементов обычно больше
            reset_func=reset_object_history
        )
        self.logger.info(f"Object pools initialized (result_pool_size={pool_size}, history_pool_size={pool_size * 2})")

    # === Инкапсуляция параметров камер и атрибутов ===

    def set_cameras_params(self, cameras_params: list[dict] | None) -> None:
        """Установить параметры камер для обработчика объектов.

        Используется контроллером вместо прямой записи в cameras_params.
        """
        self.cameras_params = cameras_params or []
        # Обновляем менеджер разметки, если он уже создан
        try:
            if self.labeling_manager is not None:
                self.labeling_manager.cameras_params = self.cameras_params
        except Exception:
            pass

    def default(self):
        pass

    def init_impl(self):
        pass

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def get_runtime_stats(self) -> dict:
        active_with_last_image = 0
        active_last_image_bytes = 0
        active_history_items = 0
        lost_with_last_image = 0
        lost_last_image_bytes = 0
        for obj in self.active_objs.objects:
            active_history_items += len(getattr(obj, "history", []) or [])
            img = getattr(getattr(obj, "last_image", None), "image", None)
            if img is not None:
                active_with_last_image += 1
                try:
                    active_last_image_bytes += int(img.nbytes)
                except Exception:
                    pass
        for obj in self.lost_objs.objects:
            img = getattr(getattr(obj, "last_image", None), "image", None)
            if img is not None:
                lost_with_last_image += 1
                try:
                    lost_last_image_bytes += int(img.nbytes)
                except Exception:
                    pass
        try:
            queue_size = self.objs_queue.qsize()
        except Exception:
            queue_size = None
        now = time.time()
        stale_sources = [
            src for src, last_ts in self._last_frame_ts_by_source.items()
            if self.source_stale_sec > 0 and (now - last_ts) > self.source_stale_sec
        ]
        maxsize = max(1, int(self.objs_queue_maxsize or 1))
        queue_pressure = None
        if queue_size is not None:
            try:
                queue_pressure = float(queue_size) / float(maxsize)
            except Exception:
                queue_pressure = None
        return {
            "active_objects": len(self.active_objs.objects),
            "lost_objects": len(self.lost_objs.objects),
            "queue_size": queue_size,
            "queue_maxsize": maxsize,
            "queue_pressure": queue_pressure,
            "history_items": active_history_items,
            "active_with_last_image": active_with_last_image,
            "active_last_image_bytes": active_last_image_bytes,
            "lost_with_last_image": lost_with_last_image,
            "lost_last_image_bytes": lost_last_image_bytes,
            "stale_source_ids": stale_sources,
            "source_stale_sec": self.source_stale_sec,
        }

    def set_params_impl(self):
        self.lost_store_time_secs = self.params.get('lost_store_time_secs', 60)
        self.history_len = self.params.get('history_len', 1)
        self.lost_thresh = self.params.get('lost_thresh', 5)
        self.max_active_objects = self.params.get('max_active_objects', 100)
        self.max_lost_objects = self.params.get('max_lost_objects', 100)
        # Saving/IO settings (can be tuned to prevent UI lag)
        self.save_object_images = bool(self.params.get('save_object_images', self.save_object_images))
        self.save_labeling_data = bool(self.params.get('save_labeling_data', self.save_labeling_data))
        try:
            self.save_min_interval_sec = float(self.params.get('save_min_interval_sec', self.save_min_interval_sec))
        except Exception:
            pass
        try:
            self.source_stale_sec = float(self.params.get('source_stale_sec', self.source_stale_sec))
        except Exception:
            pass
        # Максимальный размер очереди входящих кадров/результатов.
        # При переполнении будем выкидывать самые старые элементы (drop-oldest).
        self.objs_queue_maxsize = int(self.params.get('objs_queue_maxsize', self.objs_queue_maxsize))
        try:
            if getattr(self.objs_queue, "maxsize", 0) != self.objs_queue_maxsize:
                # Нельзя безопасно "поменять maxsize" существующей Queue, пересоздаем.
                self.objs_queue = Queue(maxsize=self.objs_queue_maxsize)
        except Exception:
            pass
        # thresholds for attributes (optional)
        attrs = self.params.get('attributes_detection', {})
        classifier = attrs.get('classifier', {})
        self._attr_conf_thresholds = classifier.get('confidence_thresholds', {})
        self._attr_time_thresholds = classifier.get('time_thresholds', {})
        self._attr_ema_alpha = classifier.get('ema_alpha', 0.6)

        # Always create AttributeManager and set params
        self.attr_manager = AttributeManager(self._attr_conf_thresholds, self._attr_time_thresholds,
                                             self._attr_ema_alpha)
        if attrs:
            self.attr_manager.set_params(attrs)

        # Инициализация пулов объектов для оптимизации памяти
        self._use_object_pool = self.params.get('use_object_pool', True)
        if self._use_object_pool:
            pool_size = self.params.get('object_pool_size', 20)
            self._init_object_pools(pool_size)

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
        if self.labeling_manager is not None:
            self.labeling_manager.stop()

        self.logger.info('Handler stopped')

    def start(self):
        self.run_flag = True
        self.handler.start()

    def put(self, data):  # Добавление данных из детектора/трекера в очередь
        # Drop-oldest при переполнении: всегда стараемся держать "самое свежее"
        try:
            if self.objs_queue.full():
                try:
                    self.objs_queue.get_nowait()
                except Exception:
                    pass
            self.objs_queue.put_nowait(data)
        except Exception:
            # Если по каким-то причинам не получилось — не ломаем основной цикл
            pass

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
        self.logger.info('Handler working: waiting for objects...')
        while self.run_flag:
            begin_it = timer()
            now = time.time()
            if (now - self._last_stale_check_ts) >= 1.0:
                self._last_stale_check_ts = now
                with self.lock:
                    self._expire_stale_source_objects(now)
            # Не замедляемся искусственно, если очередь непустая.
            # Если пустая — чуть спим, чтобы не крутить busy-loop.
            if self.objs_queue.empty():
                time.sleep(0.005)
                continue
            tracking_results = self.objs_queue.get()
            if tracking_results is None:
                continue

            # Handle both tuples [tracks, image] and Frame objects
            if isinstance(tracking_results, (tuple, list)) and len(tracking_results) == 2:
                tracks, image = tracking_results
            else:
                # Assume it's a Frame object (from attributes processors)
                tracks = None
                image = tracking_results
            # Блокируем остальные потоки для предотвращения одновременного обращения к объектам
            with self.lock:
                # self.condition.acquire()
                self._handle_active(tracks, image)
                if self.active_objs.objects:
                    self.snapshot = self.active_objs.objects
                else:
                    self.snapshot = None

                # Notify subscribers (events detectors) on each update
                for subscriber in self.subscribers:
                    try:
                        subscriber.update()
                    except Exception:
                        pass

            if self._perf_diag_env:
                try:
                    self._perf_diag_counter += 1
                    every = max(1, int(self._perf_diag_every or 60))
                    if (self._perf_diag_counter % every) == 0:
                        try:
                            qsz = self.objs_queue.qsize()
                        except Exception:
                            qsz = -1
                        self.logger.info(
                            "PerfDiag(ObjectsHandler): processed=%d, qsize=%s, active=%d, lost=%d, proc_ms=%.1f, track_id_changes=%d, missing_track_object=%d",
                            self._perf_diag_counter,
                            qsz,
                            (len(self.active_objs.objects) if self.active_objs else -1),
                            (len(self.lost_objs.objects) if self.lost_objs else -1),
                            (timer() - begin_it) * 1000.0,
                            self._diag_track_id_changes,
                            self._diag_missing_track_object,
                        )
                except Exception:
                    pass

        for subscriber in self.subscribers:
            subscriber.update()

    def _timestamp_to_datetime(self, timestamp: Union[float, datetime.datetime, None]) -> Optional[datetime.datetime]:
        """
        Convert timestamp (float or datetime) to datetime object.
        
        Args:
            timestamp: Can be float (Unix timestamp) or datetime object or None
            
        Returns:
            datetime object or None
        """
        if timestamp is None:
            return None
        if isinstance(timestamp, datetime.datetime):
            return timestamp
        if isinstance(timestamp, (int, float)):
            return datetime.datetime.fromtimestamp(timestamp)
        return None

    def _copy_frame_clock(self, obj, image) -> None:
        if image is None:
            return
        pts = getattr(image, "pts_ns", None)
        if pts is not None:
            obj.pts_ns = pts
        media = getattr(image, "media_pts_sec", None)
        if media is not None:
            obj.media_pts_sec = media

    def _event_date_str(self, obj, *, lost: bool = False) -> str:
        from evileye.core.event_time import date_folder_from_ts

        ts = obj.time_lost if lost else (obj.time_stamp or obj.time_detected)
        return date_folder_from_ts(ts)

    def _is_primary_object(self, obj):
        """Check if object is primary based on class name or ID"""
        if not self.attr_manager:
            return False

        # Get primary classes from attr_manager config
        primary_by_name = getattr(self.attr_manager, '_primary_by_name', [])
        primary_by_id = getattr(self.attr_manager, '_primary_by_id', [])

        # Use ClassManager if available
        if self.class_manager:
            # Convert primary class names to IDs using ClassManager
            primary_ids_from_names = self.class_manager.get_primary_classes_by_name(primary_by_name)
            primary_ids_from_ids = self.class_manager.get_primary_classes_by_id(primary_by_id)

            # Check if object's class_id is in any primary list
            all_primary_ids = primary_ids_from_names + primary_ids_from_ids
            return obj.class_id in all_primary_ids
        else:
            # Fallback to old logic
            # Check by class name using class_mapping if available
            if self.class_mapping:
                for name, cid in self.class_mapping.items():
                    if cid == obj.class_id and name in primary_by_name:
                        return True
            else:
                # Fallback to hardcoded class names for backward compatibility
                class_names = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"]
                if obj.class_id < len(class_names):
                    class_name = class_names[obj.class_id]
                    if class_name in primary_by_name:
                        return True

            # Check by class ID
            if obj.class_id in primary_by_id:
                return True
        return False

    def _create_default_attributes(self, obj):
        """Create default attributes for primary objects"""
        if not self.attr_manager:
            return

        # Get configured attributes from attr_manager
        attrs = getattr(self.attr_manager, '_configured_attrs', ['hard_hat', 'no_hard_hat'])

        # Create default attributes with 'none' state
        default_attributes = {}
        for attr_name in attrs:
            default_attributes[attr_name] = {
                'attr_name': attr_name,
                'state': 'none',
                'confidence_smooth': 0.0,
                'frames_present': 0,
                'total_time_ms': 0,
                'no_detect_time_ms': 0,
                'enter_count': 0,
                'enter_ts': None,
                'last_seen_ts': None,
                'ema_alpha': 0.7
            }

        obj.attributes = default_attributes

    def _ensure_all_attributes_present(self, obj):
        """Ensure all configured attributes are present in the object"""
        if not self.attr_manager:
            return

        # Get configured attributes from attr_manager
        attrs = getattr(self.attr_manager, '_configured_attrs', [])
        if not attrs:
            return

        # Initialize obj.attributes if it doesn't exist
        if not hasattr(obj, 'attributes') or obj.attributes is None:
            obj.attributes = {}

        # Add missing attributes with 'none' state
        for attr_name in attrs:
            if attr_name not in obj.attributes:
                obj.attributes[attr_name] = {
                    'name': attr_name,
                    'state': 'none',
                    'confidence_smooth': 0.0,
                    'frames_present': 0,
                    'total_time_ms': 0,
                    'no_detect_time_ms': 0,
                    'enter_count': 0,
                    'enter_ts': None,
                    'last_seen_ts': None
                }

    def _remove_track_attributes(self, obj: ObjectResult) -> None:
        if self.attr_manager is None:
            return
        track = getattr(obj, "track", None)
        track_id = getattr(track, "track_id", None) if track is not None else None
        if track_id is None:
            return
        try:
            self.attr_manager.remove_track(int(track_id))
        except Exception:
            pass

    def _release_object_to_pool(self, obj: ObjectResult) -> None:
        obj.last_image = None
        if self._use_object_pool and self._object_history_pool:
            for hist_elem in obj.history:
                if isinstance(hist_elem, ObjectResultHistory):
                    self._object_history_pool.release(hist_elem)
        if self._use_object_pool and self._object_result_pool:
            self._object_result_pool.release(obj)

    def _finalize_lost_object(self, active_obj: ObjectResult, tracking_results: TrackingResultList | None) -> None:
        if active_obj.time_lost is None:
            active_obj.time_lost = (
                self._timestamp_to_datetime(active_obj.time_stamp)
                or self._timestamp_to_datetime(getattr(tracking_results, "time_stamp", None) if tracking_results else None)
                or datetime.datetime.now()
            )
        if self.db_adapter is not None:
            try:
                self.db_adapter.update(active_obj)
            except Exception as exc:
                self.logger.error(
                    "DB update failed for lost object_id=%s source=%s: %s",
                    active_obj.object_id,
                    active_obj.source_id,
                    exc,
                    exc_info=True,
                )

        allow_save = True
        try:
            sid = int(active_obj.source_id) if active_obj.source_id is not None else None
            if sid is not None and self.save_min_interval_sec and self.save_min_interval_sec > 0:
                last_ts = self._last_save_ts_by_source.get(sid)
                now_ts = time.time()
                if last_ts is not None and (now_ts - last_ts) < self.save_min_interval_sec:
                    allow_save = False
                else:
                    self._last_save_ts_by_source[sid] = now_ts
        except Exception:
            allow_save = True

        if allow_save and self.save_object_images:
            self._save_object_images(active_obj, 'lost')

        if allow_save and self.save_labeling_data:
            try:
                full_img_path = self._get_img_path('frame', 'lost', active_obj)
                image_filename = os.path.basename(full_img_path)
                preview_filename = os.path.basename(self._get_img_path('preview', 'lost', active_obj))
                last_image = getattr(active_obj, "last_image", None)
                image_width = last_image.width if last_image is not None and hasattr(last_image, 'width') else 1920
                image_height = last_image.height if last_image is not None and hasattr(last_image, 'height') else 1080
                object_data = self.labeling_manager.create_lost_object_data(
                    active_obj, image_width, image_height, image_filename, preview_filename
                )
                self.labeling_manager.add_object_lost(object_data)
            except Exception as e:
                self.logger.error(f"Labeling data saving error for lost object: {e}")

        self._remove_track_attributes(active_obj)
        active_obj.last_image = None
        self.lost_objs.objects.append(active_obj)

    def _expire_stale_source_objects(self, now: float, *, exclude_source_id: int | None = None) -> None:
        if self.source_stale_sec <= 0:
            return
        stale_sources: set[int] = set()
        for src, last_ts in list(self._last_frame_ts_by_source.items()):
            if exclude_source_id is not None and int(src) == int(exclude_source_id):
                continue
            if (now - last_ts) > self.source_stale_sec:
                stale_sources.add(int(src))
        if not stale_sources:
            return
        remaining_active = []
        for active_obj in self.active_objs.objects:
            if active_obj.source_id in stale_sources:
                self._finalize_lost_object(active_obj, tracking_results=None)
            else:
                remaining_active.append(active_obj)
        self.active_objs.objects = remaining_active

    def _handle_active(self, tracking_results: TrackingResultList, image):
        tracking_results = ensure_tracking_result_list(tracking_results)
        for active_obj in self.active_objs.objects:
            active_obj.last_update = False

        # Handle case when tracking_results is None (from attributes processors)
        if tracking_results is None:
            # Update attributes for active objects without new tracking data
            current_ts = time.time()
            dt_ms = int((current_ts - (self._last_frame_ts.get(image.source_id, current_ts))) * 1000)
            self._last_frame_ts[image.source_id] = current_ts
            if image.source_id is not None:
                self._last_frame_ts_by_source[int(image.source_id)] = current_ts

            # Process attribute results from AttributeClassifier
            # Check both image.attr_results and tracking_data.attr_results
            attr_results_source = None
            if hasattr(image, 'attr_results') and image.attr_results:
                attr_results_source = image.attr_results
            elif hasattr(tracking_results, 'attr_results') and tracking_results.attr_results:
                attr_results_source = tracking_results.attr_results

            if attr_results_source:
                for track_id, attr_results in attr_results_source.items():
                    if self.attr_manager:
                        for attr_name, attr_info in attr_results.items():
                            detected_now = attr_info.get('detected_now', False)
                            confidence = attr_info.get('confidence', 0.0)
                            self.attr_manager.update(track_id, attr_name, detected_now, confidence, current_ts, dt_ms)

            for active_obj in self.active_objs.objects:
                # Update attributes for active objects
                if self.attr_manager:
                    attr_states = self.attr_manager.get_states(active_obj.track.track_id)
                    active_obj.attributes = {name: state.__dict__ for name, state in attr_states.items()}

                # Ensure all attributes are present for primary objects
                if self._is_primary_object(active_obj):
                    self._ensure_all_attributes_present(active_obj)
            return

        # Convert DetectionResultList to TrackingResultList if trackers are disabled
        if isinstance(tracking_results, DetectionResultList):
            tracking_result_list = TrackingResultList()
            tracking_result_list.generate_from(tracking_results)
            # Copy metadata from DetectionResultList
            tracking_result_list.source_id = tracking_results.source_id
            tracking_result_list.frame_id = tracking_results.frame_id
            tracking_result_list.time_stamp = tracking_results.time_stamp
            # Copy confidence from detections to tracks
            for i, track in enumerate(tracking_result_list.tracks):
                if i < len(tracking_results.detections):
                    track.confidence = tracking_results.detections[i].confidence
            tracking_results = tracking_result_list

        # Ensure tracking_results has tracks attribute
        if not hasattr(tracking_results, 'tracks') or tracking_results.tracks is None:
            self.logger.warning(
                f"tracking_results has no tracks attribute, skipping frame {image.frame_id if image else 'unknown'}")
            return
        try:
            source_id = getattr(tracking_results, "source_id", None)
            if source_id is not None:
                now_ts = time.time()
                self._last_frame_ts_by_source[int(source_id)] = now_ts
            current_ids = {
                int(getattr(tr, "track_id", -1))
                for tr in (tracking_results.tracks or [])
                if getattr(tr, "track_id", None) is not None
            }
            if source_id is not None:
                prev_ids = self._diag_prev_track_ids_by_source.get(source_id, set())
                if prev_ids and current_ids and prev_ids != current_ids:
                    self._diag_track_id_changes += 1
                if current_ids:
                    self._diag_prev_track_ids_by_source[source_id] = current_ids
            for tr in (tracking_results.tracks or []):
                tdata = getattr(tr, "tracking_data", None)
                if isinstance(tdata, dict) and "track_object" not in tdata:
                    self._diag_missing_track_object += 1
        except Exception:
            pass

        for track in tracking_results.tracks:
            track_object = None
            for active_obj in self.active_objs.objects:
                # track_id is per-camera in BoT-SORT; must not match across source_id.
                if (
                    active_obj.source_id == tracking_results.source_id
                    and active_obj.track is not None
                    and active_obj.track.track_id == track.track_id
                ):
                    track_object = active_obj
                    break

            if track_object:
                track_object.source_id = tracking_results.source_id
                track_object.frame_id = tracking_results.frame_id
                track_object.class_id = track.class_id
                track_object.track = track
                # Convert timestamp to datetime if needed
                track_object.time_stamp = self._timestamp_to_datetime(tracking_results.time_stamp)
                self._copy_frame_clock(track_object, image)
                # Store reference to image instead of copying to save memory
                # The image will be used for saving, then cleared when object is lost
                track_object.last_image = image
                track_object.cur_video_pos = image.current_video_position
                hist_elem = track_object.get_current_history_element(
                    history_pool=self._object_history_pool if self._use_object_pool else None
                )
                track_object.history.append(hist_elem)
                if len(track_object.history) > self.history_len:
                    old_hist = track_object.history[0]
                    del track_object.history[0]
                    if self._use_object_pool and self._object_history_pool and isinstance(
                            old_hist, ObjectResultHistory):
                        self._object_history_pool.release(old_hist)
                track_object.last_update = True
                track_object.lost_frames = 0
                track_object.last_image = None
            else:
                # Используем пул объектов для оптимизации памяти
                if self._use_object_pool and self._object_result_pool:
                    obj = self._object_result_pool.acquire()
                else:
                    obj = ObjectResult()
                obj.source_id = tracking_results.source_id
                obj.class_id = track.class_id
                # Convert timestamp to datetime if needed
                obj.time_stamp = self._timestamp_to_datetime(tracking_results.time_stamp)
                obj.time_detected = self._timestamp_to_datetime(tracking_results.time_stamp)
                self._copy_frame_clock(obj, image)
                obj.frame_id = tracking_results.frame_id
                obj.object_id = self.object_id_counter
                obj.global_id = track.tracking_data.get('global_id', None)
                # Store reference to image instead of copying to save memory
                # The image will be used for saving, then cleared when object is lost
                obj.last_image = image
                obj.cur_video_pos = image.current_video_position
                self.object_id_counter += 1
                obj.track = track
                hist_elem = obj.get_current_history_element(
                    history_pool=self._object_history_pool if self._use_object_pool else None
                )
                obj.history.append(hist_elem)
                start_insert_it = timer()
                if self.db_adapter is not None:
                    try:
                        self.db_adapter.insert(obj)
                    except Exception as exc:
                        self.logger.error(
                            "DB insert failed for object_id=%s source=%s: %s",
                            obj.object_id,
                            obj.source_id,
                            exc,
                            exc_info=True,
                        )
                end_insert_it = timer()

                # Save images/labeling for found object (throttled to avoid IO-induced backlog)
                allow_save = True
                try:
                    sid = int(obj.source_id) if obj.source_id is not None else None
                    if sid is not None and self.save_min_interval_sec and self.save_min_interval_sec > 0:
                        last_ts = self._last_save_ts_by_source.get(sid)
                        now_ts = time.time()
                        if last_ts is not None and (now_ts - last_ts) < self.save_min_interval_sec:
                            allow_save = False
                        else:
                            self._last_save_ts_by_source[sid] = now_ts
                except Exception:
                    allow_save = True

                if allow_save and self.save_object_images:
                    self._save_object_images(obj, 'detected')

                if allow_save and self.save_labeling_data:
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
                        self.logger.error(f"Labeling data saving error for found object: {e}")

                obj.last_image = None
                self.active_objs.objects.append(obj)
            # print(f"active_objs len={len(self.active_objs.objects)} size={asizeof.asizeof(self.active_objs.objects)/(1024.0*1024.0)}")
            # print(f"lost_objs len={len(self.lost_objs.objects)} size={asizeof.asizeof(self.lost_objs.objects)/(1024.0*1024.0)}")

        # Обновление атрибутов для активных объектов (если включено)
        if self.attr_manager is not None and tracking_results is not None:
            dt_ms = 0
            # оценка dt по fps/времени могла бы быть точнее; используем 33мс как дефолт
            try:
                dt_ms = int(1000.0 / max(1, getattr(image, 'fps', 30)))
            except Exception:
                dt_ms = 33
            now_ts = time.time()

            # Process attribute results from AttributeClassifier
            if hasattr(tracking_results, 'attr_results') and tracking_results.attr_results:
                for track_id, attr_results in tracking_results.attr_results.items():
                    for attr_name, attr_info in attr_results.items():
                        detected_now = attr_info.get('detected_now', False)
                        confidence = attr_info.get('confidence', 0.0)
                        self.attr_manager.update(track_id, attr_name, detected_now, confidence, now_ts, dt_ms)

            # Сохранить снимок состояний атрибутов в объекты
            for obj in self.active_objs.objects:
                if obj.source_id != tracking_results.source_id:
                    continue

                # Сохранить снимок состояний в объект
                attr_states = self.attr_manager.get_states(obj.track.track_id)
                obj.attributes = {k: vars(v) for k, v in attr_states.items()}

                # Убедиться, что все настроенные атрибуты присутствуют в объекте
                if self._is_primary_object(obj):
                    self._ensure_all_attributes_present(obj)

        filtered_active_objects = []
        for active_obj in self.active_objs.objects:
            if not active_obj.last_update and active_obj.source_id == tracking_results.source_id:
                active_obj.lost_frames += 1
                if active_obj.lost_frames >= self.lost_thresh:
                    self._finalize_lost_object(active_obj, tracking_results)
                else:
                    filtered_active_objects.append(active_obj)
            else:
                filtered_active_objects.append(active_obj)
        self.active_objs.objects = filtered_active_objects

        start_index_for_remove = None
        for i in reversed(range(len(self.lost_objs.objects))):
            if (datetime.datetime.now() - self.lost_objs.objects[
                i].time_lost).total_seconds() > self.lost_store_time_secs:
                start_index_for_remove = i
                break
        if start_index_for_remove is not None:
            for obj in self.lost_objs.objects[:start_index_for_remove]:
                self._release_object_to_pool(obj)
            self.lost_objs.objects = self.lost_objs.objects[start_index_for_remove:]

        if len(self.active_objs.objects) > self.max_active_objects:
            for obj in self.active_objs.objects[:-self.max_active_objects]:
                self._release_object_to_pool(obj)
            self.active_objs.objects = self.active_objs.objects[-self.max_active_objects:]
        if len(self.lost_objs.objects) > self.max_lost_objects:
            for obj in self.lost_objs.objects[:-self.max_lost_objects]:
                self._release_object_to_pool(obj)
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
                from evileye.utils.camera_event_label import media_url_without_credentials

                fields_for_saving['camera_full_address'] = media_url_without_credentials(
                    str(camera.get('camera') or '')
                )
                break

        # Use list() instead of deepcopy for bounding box (list of numbers)
        fields_for_saving['bounding_box'] = list(fields_for_saving['bounding_box'])
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

        # Use list() instead of deepcopy for bounding box (list of numbers)
        fields_for_updating['lost_bounding_box'] = list(fields_for_updating['lost_bounding_box'])
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
            self.logger.error(f"Object images saving error: {e}")

    def _save_image(self, image, box, image_type, obj_event_type, obj):
        """Save image to file system independent of database - using same logic as database journal"""
        try:
            # Guard against transient None/empty frames during pipeline restarts.
            # These can happen for VideoFile loop_play restarts and should not be treated as errors.
            if image is None or getattr(image, "image", None) is None:
                return
            try:
                # OpenCV treats empty arrays as invalid too.
                if hasattr(image.image, "size") and image.image.size == 0:
                    return
            except Exception:
                pass

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

            # Save clean images without any debug overlays
            if image_type == 'preview':
                preview_width = int(self.db_params.get('preview_width', 300))
                preview_height = int(self.db_params.get('preview_height', 150))
                preview = ImageStorageService.resize_preserving_aspect(
                    image.image.copy(),
                    preview_width,
                    preview_height,
                )
                saved = cv2.imwrite(full_img_path, preview)
            else:
                # Save original frame without any graphical info
                saved = cv2.imwrite(full_img_path, image.image)

            if not saved:
                self.logger.error(f'ERROR: Failed to save image file {full_img_path}')

        except Exception as e:
            # Keep as error (should be rare after guards), but avoid cascading failures.
            self.logger.error(f"Image saving error: {e}")

    def _get_img_path(self, image_type, obj_event_type, obj):
        # Use default image directory if database is not available
        if 'image_dir' in self.db_params and self.db_params['image_dir']:
            save_dir = self.db_params['image_dir']
        else:
            save_dir = 'EvilEyeData'  # Default directory
        detections_dir = os.path.join(save_dir, 'Detections')
        cur_date_str = self._event_date_str(obj, lost=(obj_event_type == 'lost'))

        current_day_path = os.path.join(detections_dir, cur_date_str)
        images_dir = os.path.join(current_day_path, 'Images')
        # New folders for objects: FoundFrames/FoundPreviews/LostFrames/LostPreviews
        if obj_event_type == 'detected':
            if image_type == 'preview':
                subdir = 'FoundPreviews'
            else:
                subdir = 'FoundFrames'
        elif obj_event_type == 'lost':
            if image_type == 'preview':
                subdir = 'LostPreviews'
            else:
                subdir = 'LostFrames'
        else:
            # Fallback for other types
            tag = obj_event_type
            subdir = f"{tag}{'Previews' if image_type == 'preview' else 'Frames'}"
        obj_type_path = os.path.join(images_dir, subdir)
        # obj_event_path = os.path.join(current_day_path, obj_event_type)
        if not os.path.exists(detections_dir):
            os.makedirs(detections_dir, exist_ok=True)
        if not os.path.exists(current_day_path):
            os.makedirs(current_day_path, exist_ok=True)
        if not os.path.exists(images_dir):
            os.makedirs(images_dir, exist_ok=True)
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
            dt = self._timestamp_to_datetime(obj.time_stamp)
            if dt is None:
                dt = datetime.datetime.now()
            timestamp = dt.strftime('%Y-%m-%d_%H-%M-%S.%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{source_name}_{image_type}.jpeg')
        elif obj_event_type == 'lost':
            dt = self._timestamp_to_datetime(obj.time_lost)
            if dt is None:
                dt = datetime.datetime.now()
            timestamp = dt.strftime('%Y-%m-%d_%H-%M-%S-%f')
            img_path = os.path.join(obj_type_path, f'{timestamp}_{source_name}_{image_type}.jpeg')
        return os.path.relpath(img_path, save_dir)
