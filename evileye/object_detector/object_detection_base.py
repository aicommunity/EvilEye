from __future__ import annotations

from abc import ABC, abstractmethod
from queue import Queue
import threading
from time import sleep
from typing import Optional

from ..core.base_class import EvilEyeBase
from ..core.class_manager import ClassManager
from ..core.frame import CaptureImage

from .constants import (
    DEFAULT_INPUT_QUEUE_SIZE,
    DEFAULT_NUM_DETECTION_THREADS,
    DEFAULT_STRIDE,
    MODEL_PRELOAD_TIMEOUT,
    MODEL_READY_TIMEOUT,
    PROCESSING_SLEEP_INTERVAL,
    THREAD_START_DELAY,
    DEFAULT_MAX_FRAME_AGE_MS,
    DEFAULT_INFERENCE_SIZE,
)


class DetectionResult:
    def __init__(self):
        self.bounding_box = []
        self.confidence = 0.0
        self.class_id = None
        self.detection_data = dict()  # internal detection data


class DetectionResultList:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.detections: list[DetectionResult] = []


class ObjectDetectorBase(EvilEyeBase, ABC):
    ResultType = DetectionResultList

    def __init__(self):
        super().__init__()

        self.run_flag = False
        # Increased queue size to prevent overflow during startup when models are loading
        self.queue_in = Queue(maxsize=DEFAULT_INPUT_QUEUE_SIZE)
        self.queue_out = Queue()
        self.source_ids = []
        self.classes = []
        self.stride = DEFAULT_STRIDE
        self.roi = [[]]
        self.queue_dropped_id = Queue()

        self.num_detection_threads = DEFAULT_NUM_DETECTION_THREADS
        self.detection_threads = []
        self.thread_counter = 0

        self.processing_thread = None

        self.model_class_mapping = None
        self._model_class_mapping_cache: Optional[dict] = None
        self.class_manager = None  # Will be set by Controller
        self._roi_cache: dict[int, list[list[int]]] = {}
        
        # Performance metrics
        self._metrics = {
            'total_frames_processed': 0,
            'total_frames_dropped': 0,
            'total_stale_frames_skipped': 0,
            'total_inference_time_ms': 0.0,
            'max_queue_size': 0,
            'last_metrics_log_time': 0.0,
        }

    def put(self, image: CaptureImage) -> bool:
        """Put image into input queue for processing."""
        try:
            self.queue_in.put_nowait(image)
            return True
        except Exception:
            self.logger.warning(
                f"Failed to put image {image.source_id}:{image.frame_id} to ObjectDetection queue. Queue is full."
            )
            return False

    def get(self):
        """Get detection result from output queue."""
        try:
            return self.queue_out.get_nowait()
        except Exception:
            return None

    def get_model_class_mapping(self) -> Optional[dict]:
        """Get model class mapping with caching."""
        if self._model_class_mapping_cache is not None:
            return self._model_class_mapping_cache

        if len(self.detection_threads) > 0:
            model_class_mapping = self.detection_threads[0].get_model_class_mapping()
            if self.model_class_mapping is not None and model_class_mapping is not None and self.model_class_mapping != model_class_mapping:
                self.logger.info(f"Model class mapping overridden by internal data: {model_class_mapping}")
                self.model_class_mapping = model_class_mapping
            elif model_class_mapping is not None and self.model_class_mapping is None:
                # Auto-update from thread if not set manually
                self.model_class_mapping = model_class_mapping
                self.logger.info(f"Auto-updated model_class_mapping from detection thread: {model_class_mapping}")
                
                # CRITICAL: Update classes after getting model_class_mapping
                self._update_classes_after_model_loading()
            elif model_class_mapping is not None and self.model_class_mapping is not None:
                # Model is loaded, check if we need to update classes
                self._check_and_update_classes_if_needed()
        else:
            self.model_class_mapping = None

        if self.model_class_mapping is not None:
            self._model_class_mapping_cache = self.model_class_mapping.copy()
        return self.model_class_mapping
    
    def _process_classes_parameter(self):
        """Process classes parameter to support both class IDs and class names"""
        if not self.classes:
            return
            
        # Store original classes for reference
        original_classes = self.classes.copy()
        
        # Use ClassManager if available, otherwise fallback to old logic
        if self.class_manager:
            self.classes = self.class_manager.convert_classes_to_ids(self.classes)
            if original_classes != self.classes:
                self.logger.info(f"Classes updated from {original_classes} to {self.classes} using ClassManager")
        else:
            # Fallback to old logic
            if all(isinstance(cls, str) for cls in self.classes):
                # Classes are names - convert to IDs if model_class_mapping is available
                if self.model_class_mapping:
                    self.classes = [self.model_class_mapping.get(name, -1) for name in self.classes]
                    # Remove invalid class names (not found in mapping)
                    self.classes = [cls_id for cls_id in self.classes if cls_id != -1]
                    if len(self.classes) != len([cls for cls in original_classes if isinstance(cls, str)]):
                        self.logger.warning(f"Warning: Some class names not found in model mapping: {original_classes}")
                else:
                    # Keep names temporarily; they will be converted later when mapping arrives
                    # This prevents dropping all detections before mapping becomes available
                    self.logger.warning(f"Warning: Class names provided but model_class_mapping unavailable yet: {self.classes}")
            elif all(isinstance(cls, int) for cls in self.classes):
                # Classes are IDs - keep as is
                pass
            else:
                # Mixed types - convert all to strings and treat as names
                self.logger.warning(f"Warning: Mixed class types detected, treating all as names: {self.classes}")
                self.classes = [str(cls) for cls in self.classes]
                if self.model_class_mapping:
                    self.classes = [self.model_class_mapping.get(name, -1) for name in self.classes]
                    self.classes = [cls_id for cls_id in self.classes if cls_id != -1]
    
    def update_classes_from_model_mapping(self):
        """Update classes parameter after model_class_mapping is available"""
        if self.model_class_mapping and self.classes:
            # Re-process classes parameter with updated mapping
            original_classes = self.classes.copy()
            self._process_classes_parameter()
            if original_classes != self.classes:
                self.logger.info(f"Classes updated from {original_classes} to {self.classes} using model mapping")
    
    def set_class_manager(self, class_manager: ClassManager):
        """Set the class manager for this detector"""
        self.class_manager = class_manager
        # Re-process classes with new class manager
        if self.classes:
            self._process_classes_parameter()
    
    def _update_classes_after_model_loading(self):
        """Update classes after model is loaded and model_class_mapping is available"""
        if not self.model_class_mapping:
            return
            
        # Store original classes from params for reference
        original_classes = self.params.get('classes', [])
        if not original_classes:
            return
            
        self.logger.info(f"Updating classes after model loading. Original: {original_classes}")
        
        # Re-process classes with now-available model_class_mapping
        if all(isinstance(cls, str) for cls in original_classes):
            # Classes are names - convert to IDs using model_class_mapping
            new_classes = [self.model_class_mapping.get(name, -1) for name in original_classes]
            new_classes = [cls_id for cls_id in new_classes if cls_id != -1]
            
            if new_classes != self.classes:
                self.logger.info(f"Classes updated from {self.classes} to {new_classes} using model mapping")
                self.classes = new_classes
                
                # Update classes in all detection threads
                self._update_threads_classes()
            else:
                self.logger.info(f"Classes already correct: {self.classes}")
        else:
            self.logger.info(f"Classes are IDs, conversion not needed: {self.classes}")
    
    def _update_threads_classes(self):
        """Update classes in all detection threads"""
        for thread in self.detection_threads:
            if hasattr(thread, 'classes'):
                thread.classes = self.classes.copy()
                self.logger.info(f"Thread classes updated to: {thread.classes}")
    
    def _check_and_update_classes_if_needed(self):
        """Check if classes need to be updated and update them if necessary"""
        if not self.model_class_mapping:
            return
            
        # Store original classes from params for reference
        original_classes = self.params.get('classes', [])
        if not original_classes:
            return
            
        # Check if we have string classes that need conversion
        if all(isinstance(cls, str) for cls in original_classes):
            # Convert to IDs using current model_class_mapping
            new_classes = [self.model_class_mapping.get(name, -1) for name in original_classes]
            new_classes = [cls_id for cls_id in new_classes if cls_id != -1]
            
            # Check if classes are different from current
            if new_classes != self.classes:
                self.logger.info(f"Late update: classes from {self.classes} to {new_classes} using model mapping")
                self.classes = new_classes
                
                # Update classes in all detection threads
                self._update_threads_classes()

    def get_dropped_ids(self) -> list:
        """Get all dropped frame IDs from the queue."""
        res = []
        while True:
            try:
                res.append(self.queue_dropped_id.get_nowait())
            except Exception:
                break
        return res

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self) -> list:
        return self.source_ids

    def set_params_impl(self):
        super().set_params_impl()
        self.roi = self.params.get('roi', [[]])
        self.classes = self.params.get('classes', [])
        self.stride = self.params.get('vid_stride', DEFAULT_STRIDE)
        self.source_ids = self.params.get('source_ids', [])
        self.num_detection_threads = self.params.get('num_detection_threads', DEFAULT_NUM_DETECTION_THREADS)
        self.model_class_mapping = self.params.get('model_class_mapping', None)
        self._model_class_mapping_cache = None
        
        # Frame freshness check - maximum age of frame before dropping (in seconds)
        max_frame_age_ms = self.params.get('max_frame_age_ms', DEFAULT_MAX_FRAME_AGE_MS)
        self.max_frame_age_sec = max_frame_age_ms / 1000.0 if max_frame_age_ms > 0 else 0
        
        # Process classes parameter - support both class IDs and class names
        self._process_classes_parameter()

    # ===== ROI Editor API (can be overridden by derived detectors) =====
    def get_rois_for_source(self, source_id: int) -> list[list[int]]:
        """
        Return ROI list for source in [x, y, w, h] format (cached).
        Default: try to read from self.roi structure like [[... for src0], [... for src1], ...]
        """
        if source_id in self._roi_cache:
            return self._roi_cache[source_id]
        try:
            if not isinstance(self.roi, list) or len(self.roi) == 0:
                res: list[list[int]] = []
            elif isinstance(self.source_ids, list) and source_id in self.source_ids:
                idx = self.source_ids.index(source_id)
                if isinstance(self.roi, list) and idx < len(self.roi) and isinstance(self.roi[idx], list):
                    res = [list(map(int, r)) for r in self.roi[idx]]
                else:
                    res = []
            elif len(self.roi) > 0 and isinstance(self.roi[0], list):
                res = [list(map(int, r)) for r in self.roi[0]]
            else:
                res = []
            self._roi_cache[source_id] = res
            return res
        except Exception:
            return []

    def set_rois_for_source(self, source_id: int, rois_xyxy: list[list[int]]) -> None:
        """
        Update ROI for source. Input in [x1, y1, x2, y2]; convert to [x, y, w, h] for storage.
        Default: write back to self.roi keeping per-source structure if possible.
        """
        try:
            rois_xywh = []
            for r in rois_xyxy:
                if len(r) == 4:
                    x1, y1, x2, y2 = map(int, r)
                    # Interpret input as inclusive boundaries: width = x2 - x1 + 1
                    w = max(0, x2 - x1 + 1)
                    h = max(0, y2 - y1 + 1)
                    if w <= 0 or h <= 0:
                        continue
                    rois_xywh.append([x1, y1, w, h])
            if source_id in self.source_ids:
                idx = self.source_ids.index(source_id)
                # Ensure structure large enough
                if not isinstance(self.roi, list):
                    self.roi = []
                while len(self.roi) <= idx:
                    self.roi.append([])
                self.roi[idx] = rois_xywh
            else:
                # Fallback to first
                if not isinstance(self.roi, list) or len(self.roi) == 0:
                    self.roi = [rois_xywh]
                else:
                    self.roi[0] = rois_xywh

            # Clear cache for this source
            self._roi_cache.pop(source_id, None)

            # Notify worker threads/detector about ROI change
            self._on_rois_updated_for_source(source_id)
        except Exception:
            pass

    def _on_rois_updated_for_source(self, source_id: int) -> None:
        """Hook to notify worker threads or internal components about ROI change."""
        try:
            # Try to update in threads if they support the corresponding method
            for t in getattr(self, 'detection_threads', []) or []:
                try:
                    if hasattr(t, 'set_rois_for_source'):
                        # Pass current ROI for source_id in xywh format
                        rois = self.get_rois_for_source(source_id)
                        t.set_rois_for_source(source_id, rois)
                    elif hasattr(t, 'roi'):
                        # Global update
                        t.roi = self.roi
                except Exception:
                    continue
        except Exception:
            pass

    def get_params_impl(self):
        params = dict()
        params['roi'] = self.roi
        params['classes'] = self.classes
        params['vid_stride'] = self.stride
        params['source_ids'] = self.source_ids
        params['num_detection_threads'] = self.num_detection_threads
        params['model_class_mapping'] = self.model_class_mapping
        return params

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info['run_flag'] = self.run_flag
        debug_info['roi'] = self.roi
        debug_info['classes'] = self.classes
        debug_info['source_ids'] = self.source_ids

    def start(self):
        self.run_flag = True
        if self.processing_thread:
            self.processing_thread.start()
        # Pre-load models in detection threads to avoid queue overflow
        # Models are loaded lazily in _process_impl, but we want them ready before sources start
        # Wait a bit for threads to start, then preload models
        import time
        time.sleep(MODEL_PRELOAD_TIMEOUT)
        self._preload_models()
    
    def _preload_models(self):
        """
        Pre-load models in all detection threads by sending synthetic images through the processing pipeline.
        This ensures models are loaded in the processing thread, not the initialization thread.
        
        Note: Warmup is non-blocking and optional. If warmup fails, models will still load on first use.
        """
        import time
        import threading
        
        if not self.detection_threads:
            self.logger.debug("No detection threads available for pre-loading")
            return
        
        self.logger.info(f"Starting warmup for {len(self.detection_threads)} detection thread(s)...")
        
        # Запустить warmup в отдельном потоке, чтобы не блокировать инициализацию
        def warmup_thread():
            successful_loads = 0
            failed_loads = 0
            
            for i, thread in enumerate(self.detection_threads):
                try:
                    thread_name = thread.__class__.__name__
                    model_name = getattr(thread, 'model_name', 'unknown')
                    self.logger.debug(f"Warming up model in detection thread {i} ({thread_name}): {model_name}")
                    
                    # Warmup через штатный пайплайн - модель загрузится в потоке обработки
                    # Используем короткий таймаут, чтобы не блокировать надолго
                    if self._warmup_model(thread, i, timeout=10.0):
                        successful_loads += 1
                        self.logger.info(f"Model warmup completed for thread {i} ({thread_name})")
                    else:
                        failed_loads += 1
                        self.logger.debug(f"Model warmup timeout/failed for thread {i} ({thread_name}). "
                                        f"Model will be loaded on first use.")
                except Exception as e:
                    thread_name = thread.__class__.__name__
                    self.logger.warning(f"Error during model warmup for thread {i} ({thread_name}): {e}")
                    self.logger.debug(f"Warmup error context", exc_info=True)
                    failed_loads += 1
                    # Thread will continue, model can be loaded later
            
            # Final warmup statistics
            if successful_loads > 0:
                self.logger.info(f"Model warmup completed: {successful_loads} successful, {failed_loads} failed")
            elif failed_loads > 0:
                self.logger.debug(f"Model warmup completed with errors: {failed_loads} threads failed. "
                                f"Models will be loaded on first use if possible.")
        
        # Запустить warmup в фоновом потоке
        warmup_thread_obj = threading.Thread(target=warmup_thread, daemon=True)
        warmup_thread_obj.start()
    
    def _warmup_model(self, thread, thread_index: int, timeout: float = 10.0) -> bool:
        """
        Прогреть модель синтетическим изображением через штатный пайплайн обработки.
        Модель загрузится в потоке обработки, а не в потоке инициализации.
        
        Args:
            thread: Detection thread instance
            thread_index: Index of the thread for logging
            timeout: Таймаут для warmup в секундах (по умолчанию 10 секунд)
            
        Returns:
            True если warmup успешен, False в противном случае
        """
        import numpy as np
        import time
        
        try:
            # Получить размер изображения для инференса из параметров
            imgsz = thread.inf_params.get('imgsz', DEFAULT_INFERENCE_SIZE) if hasattr(thread, 'inf_params') else DEFAULT_INFERENCE_SIZE
            
            # Создать синтетическое изображение нужного размера (минимум 1x1, чтобы избежать проблем)
            if imgsz <= 0:
                imgsz = DEFAULT_INFERENCE_SIZE
            # Создать не чисто черное изображение, а с небольшим шумом, чтобы избежать проблем с делением на ноль
            # Некоторые модели могут иметь проблемы с чисто черными изображениями
            synthetic_image_array = np.ones((imgsz, imgsz, 3), dtype=np.uint8) * 128  # Серое изображение вместо черного
            
            # Создать CaptureImage объект с нужными полями
            synthetic_capture_image = CaptureImage()
            synthetic_capture_image.image = synthetic_image_array
            # Использовать первый source_id из списка или 0 по умолчанию
            synthetic_capture_image.source_id = self.source_ids[0] if self.source_ids else 0
            synthetic_capture_image.frame_id = -1  # Специальный ID для warmup кадра
            synthetic_capture_image.time_stamp = time.time()
            synthetic_capture_image.current_video_frame = None
            synthetic_capture_image.current_video_position = None
            
            self.logger.debug(f"Warming up model in thread {thread_index} with {imgsz}x{imgsz} synthetic image via processing pipeline")
            
            # Положить синтетическое изображение в очередь обработки потока
            # Это запустит штатный пайплайн: queue_in -> _process_impl() -> init_detection_implementation() -> process_stride() -> predict()
            success, dropped_id = thread.put(synthetic_capture_image, force=True)
            if not success:
                self.logger.debug(f"Failed to put warmup image into thread {thread_index} queue")
                return False
            
            # Ждать результат из общей выходной очереди детектора
            # Результат будет в формате [DetectionResultList, CaptureImage]
            start_time = time.time()
            
            while time.time() - start_time < timeout:
                try:
                    result = self.queue_out.get(timeout=0.5)  # Короткий таймаут для частых проверок
                    if result and len(result) >= 2:
                        detection_result_list, result_image = result
                        # Проверить, что это наш warmup кадр
                        if (hasattr(result_image, 'frame_id') and 
                            result_image.frame_id == -1 and
                            result_image.source_id == synthetic_capture_image.source_id):
                            # Warmup успешен - модель загружена и обработала кадр
                            self.logger.debug(f"Warmup result received for thread {thread_index}")
                            # Очистить результат из памяти
                            del result
                            return True
                        else:
                            # Это не наш warmup кадр, вернуть его обратно в очередь
                            try:
                                self.queue_out.put_nowait(result)
                            except Exception:
                                # Если очередь переполнена, просто пропустить этот результат
                                pass
                except Exception:
                    # Таймаут или ошибка - продолжить ожидание
                    continue
            
            # Таймаут - warmup не завершился (это нормально, модель загрузится при первом использовании)
            self.logger.debug(f"Warmup timeout for thread {thread_index} after {timeout}s (model will load on first use)")
            return False
            
        except Exception as e:
            self.logger.debug(f"Error during model warmup for thread {thread_index}: {e}")
            return False
    
    def is_ready(self, timeout: float = MODEL_READY_TIMEOUT) -> bool:
        """
        Check if detector is ready to process frames (models loaded).
        Returns True if all detection threads have loaded their models.
        
        Note: For multiprocessing models (yolo_mp), model is in worker process,
        so we check if mp_control is initialized instead.
        
        Note: Warmup is optional and non-blocking - we only check if models are loaded.
        """
        import time
        start_time = time.time()
        while time.time() - start_time < timeout:
            if not self.is_inited:
                time.sleep(THREAD_START_DELAY)
                continue
            if not self.detection_threads:
                time.sleep(THREAD_START_DELAY)
                continue
            # Check if all detection threads are started and ready to process
            # Note: Models load lazily in processing thread, so we just check that threads are running
            all_ready = True
            for thread in self.detection_threads:
                # Проверяем что поток запущен
                if not hasattr(thread, 'run_flag') or not thread.run_flag:
                    all_ready = False
                    break
                # Для multiprocessing моделей проверяем mp_control
                if hasattr(thread, 'mp_control'):
                    if thread.mp_control is None:
                        all_ready = False
                        break
                # Для обычных моделей проверяем что поток обработки запущен
                # Модель загрузится лениво при первом кадре
                if hasattr(thread, 'processing_thread'):
                    if not thread.processing_thread or not thread.processing_thread.is_alive():
                        all_ready = False
                        break
            if all_ready:
                return True
            time.sleep(THREAD_START_DELAY)
        return False

    def stop(self):
        self.run_flag = False
        try:
            self.queue_in.put_nowait(None)
        except Exception:
            self.queue_in.put(None)
        # self.queue_in.put('STOP')
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        self.logger.info('Detection stopped')

    def init_impl(self):
        self.processing_thread = threading.Thread(target=self._process_impl)

    def release_impl(self):
        for i in range(len(self.detection_threads)):
            self.detection_threads[i].stop()

        self.detection_threads = []
        del self.processing_thread
        self.processing_thread = None

    def default(self):
        """Reset detector to default state."""
        self.stride = DEFAULT_STRIDE

    def reset_impl(self):
        pass


class ModelBasedDetectorBase(ObjectDetectorBase):
    """
    Base class for model-based detectors (YOLO, RTDETR, RFDETR, YOLO_MP).
    Contains common logic for all detectors that use ML models.
    """

    def __init__(self):
        super().__init__()
        self.model_name: Optional[str] = None

    @abstractmethod
    def _get_detection_thread_type(self) -> str:
        """Return the detection thread type identifier for this detector."""
        raise NotImplementedError

    @abstractmethod
    def _get_default_model_name(self) -> str:
        """Return default model name for this detector."""
        raise NotImplementedError

    def init_impl(self):
        """Initialize detector and create detection threads."""
        super().init_impl()
        self.detection_threads = []

        # Local imports to avoid circular imports
        from .config import InferenceParams
        from .detection_thread_factory import DetectionThreadFactory

        inf_params = InferenceParams.from_dict(self.params)
        thread_type = self._get_detection_thread_type()

        for i in range(self.num_detection_threads):
            model_path = self._resolve_model_path(self.model_name or self._get_default_model_name())
            logger_name = f"det{i}"
            thread = DetectionThreadFactory.create_thread(
                thread_type,
                model_path,
                self.stride,
                self.classes,
                self.source_ids,
                self.roi,
                inf_params.to_dict(),
                self.queue_out,
                logger_name=logger_name,
                parent_logger=self.logger,
            )
            # Установить ссылку на родительский детектор для передачи метрик
            if hasattr(thread, 'queue_out'):
                thread.queue_out._parent_detector = self
            thread.start()
            self.detection_threads.append(thread)
        return True

    def _get_least_loaded_thread(self) -> int:
        """
        Найти thread с наименьшей загрузкой очереди.
        
        Returns:
            Индекс thread с наименьшей загрузкой
        """
        if not self.detection_threads:
            return 0
        
        min_queue_size = float('inf')
        least_loaded_idx = 0
        
        for i, thread in enumerate(self.detection_threads):
            if hasattr(thread, 'queue_in'):
                queue_size = thread.queue_in.qsize()
                if queue_size < min_queue_size:
                    min_queue_size = queue_size
                    least_loaded_idx = i
        
        return least_loaded_idx

    def _resolve_model_path(self, model_name: str) -> str:
        """Resolve relative model path to absolute path."""
        import os

        if not os.path.isabs(model_name):
            return os.path.join(os.getcwd(), model_name)
        return model_name

    def set_params_impl(self):
        super().set_params_impl()
        if self.model_name is None:
            self.model_name = self._get_default_model_name()
        self.model_name = self.params.get("model", self.model_name)

    def get_params_impl(self):
        params = super().get_params_impl()
        params["model"] = self.model_name
        return params

    def _log_performance_metrics(self):
        """Логировать метрики производительности"""
        metrics = self._metrics
        total_processed = metrics['total_frames_processed']
        total_dropped = metrics['total_frames_dropped']
        total_stale = metrics['total_stale_frames_skipped']
        max_queue = metrics['max_queue_size']
        
        # Вычислить текущие размеры очередей threads
        thread_queue_sizes = []
        for thread in self.detection_threads:
            if hasattr(thread, 'queue_in'):
                thread_queue_sizes.append(thread.queue_in.qsize())
        
        avg_inference_time = 0.0
        if total_processed > 0:  # Защита от деления на ноль
            avg_inference_time = metrics['total_inference_time_ms'] / total_processed
        
        self.logger.info(
            f"Detector performance metrics: "
            f"processed={total_processed}, "
            f"dropped={total_dropped}, "
            f"stale_skipped={total_stale}, "
            f"max_queue_size={max_queue}, "
            f"thread_queue_sizes={thread_queue_sizes}, "
            f"avg_inference_time_ms={avg_inference_time:.2f}"
        )
    
    def get_performance_metrics(self) -> dict:
        """
        Получить текущие метрики производительности.
        
        Returns:
            Словарь с метриками производительности
        """
        thread_queue_sizes = []
        for thread in self.detection_threads:
            if hasattr(thread, 'queue_in'):
                thread_queue_sizes.append(thread.queue_in.qsize())
        
        metrics = self._metrics.copy()
        metrics['current_queue_size'] = self.queue_in.qsize()
        metrics['thread_queue_sizes'] = thread_queue_sizes
        metrics['output_queue_size'] = self.queue_out.qsize()
        
        # Вычислить среднее время инференса (с защитой от деления на ноль)
        if metrics['total_frames_processed'] > 0:
            metrics['avg_inference_time_ms'] = metrics['total_inference_time_ms'] / metrics['total_frames_processed']
        else:
            metrics['avg_inference_time_ms'] = 0.0
        
        return metrics

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info["model_name"] = self.model_name
        # Добавить метрики в debug_info
        debug_info["performance_metrics"] = self.get_performance_metrics()

    def default(self):
        super().default()
        self.model_name = None
        self.params.clear()

    def _process_impl(self):
        """Main processing loop that distributes images to detection threads."""
        import time
        
        while self.run_flag:
            if not self.is_inited:
                sleep(PROCESSING_SLEEP_INTERVAL)
                continue

            try:
                image = self.queue_in.get(timeout=PROCESSING_SLEEP_INTERVAL)
            except Exception:
                continue
            if not image:
                continue

            # Обновить метрики размера очереди
            current_queue_size = self.queue_in.qsize()
            if current_queue_size > self._metrics['max_queue_size']:
                self._metrics['max_queue_size'] = current_queue_size

            # Проверка актуальности кадра
            if self.max_frame_age_sec > 0 and image.time_stamp:
                try:
                    # Конвертировать timestamp в float если нужно
                    if isinstance(image.time_stamp, (int, float)):
                        frame_timestamp = float(image.time_stamp)
                    else:
                        # Предполагаем datetime или другой формат
                        frame_timestamp = getattr(image.time_stamp, 'timestamp', lambda: time.time())()
                    
                    frame_age = time.time() - frame_timestamp
                    if frame_age > self.max_frame_age_sec:
                        self._metrics['total_stale_frames_skipped'] += 1
                        self.logger.debug(f"Skipping stale frame {image.frame_id} from source {image.source_id} (age: {frame_age:.2f}s > {self.max_frame_age_sec:.2f}s)")
                        continue
                except Exception as e:
                    # Если проверка актуальности не удалась, обрабатываем кадр (fallback)
                    self.logger.debug(f"Frame freshness check failed, processing frame anyway: {e}")

            # Умное распределение нагрузки - выбрать thread с наименьшей загрузкой
            thread_idx = self._get_least_loaded_thread()
            res, dropped_id = self.detection_threads[thread_idx].put(image, force=True)
            if dropped_id:
                self._metrics['total_frames_dropped'] += 1
                try:
                    self.queue_dropped_id.put_nowait(dropped_id)
                except Exception:
                    pass
            else:
                self._metrics['total_frames_processed'] += 1
            
            # Обновить thread_counter для совместимости (но используется умное распределение)
            self.thread_counter = (thread_idx + 1) % self.num_detection_threads
            
            # Периодическое логирование метрик (каждые 5 секунд)
            current_time = time.time()
            if current_time - self._metrics['last_metrics_log_time'] >= 5.0:
                self._log_performance_metrics()
                self._metrics['last_metrics_log_time'] = current_time
