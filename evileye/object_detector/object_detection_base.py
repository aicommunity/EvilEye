from abc import ABC

from ..core.frame import CaptureImage
from ..core.class_manager import ClassManager

from ..core.base_class import EvilEyeBase
from queue import Queue
import threading
from time import sleep


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
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.source_ids = []
        self.classes = []
        self.stride = 1  # Параметр скважности
        self.roi = [[]]
        self.queue_dropped_id = Queue()

        self.num_detection_threads = 3
        self.detection_threads = []
        self.thread_counter = 0

        self.processing_thread = None

        self.model_class_mapping = None
        self.class_manager = None  # Will be set by Controller

    def put(self, image: CaptureImage) -> bool:
        if not self.queue_in.full():
            self.queue_in.put(image)
            return True
        self.logger.warning(f"Failed to put image {image.source_id}:{image.frame_id} to ObjectDetection queue. Queue is full.")
        return False

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_model_class_mapping(self) -> dict|None:
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
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_queue_out_size(self) -> int:
        return self.queue_out.qsize()

    def get_source_ids(self) -> list:
        return self.source_ids

    def set_params_impl(self):
        super().set_params_impl()
        self.roi = self.params.get('roi', [[]])
        self.classes = self.params.get('classes', [])
        self.stride = self.params.get('vid_stride', 1)
        self.source_ids = self.params.get('source_ids', [])
        self.num_detection_threads = self.params.get('num_detection_threads', 3)
        self.model_class_mapping = self.params.get('model_class_mapping', None)
        
        # Process classes parameter - support both class IDs and class names
        self._process_classes_parameter()

    # ===== ROI Editor API (can be overridden by derived detectors) =====
    def get_rois_for_source(self, source_id: int) -> list[list[int]]:
        """
        Return ROI list for source in [x, y, w, h] format.
        Default: try to read from self.roi structure like [[... for src0], [... for src1], ...]
        """
        try:
            if not isinstance(self.roi, list) or len(self.roi) == 0:
                return []
            # Heuristic: if roi structure is per-source list, pick first list
            # Otherwise, try to find by index of source_id in self.source_ids
            # Если структура ROI пер-источник и указаны source_ids — выбрать по индексу
            if isinstance(self.source_ids, list) and source_id in self.source_ids:
                idx = self.source_ids.index(source_id)
                if isinstance(self.roi, list) and idx < len(self.roi) and isinstance(self.roi[idx], list):
                    return [list(map(int, r)) for r in self.roi[idx]]
            # Если ROI едины для всех источников (список списков), берём первый
            if len(self.roi) > 0 and isinstance(self.roi[0], list):
                return [list(map(int, r)) for r in self.roi[0]]
        except Exception:
            pass
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
                    # Интерпретируем вход как включительные границы: width = x2 - x1 + 1
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
            # Уведомляем рабочие потоки/детектор о смене ROI
            self._on_rois_updated_for_source(source_id)
        except Exception:
            pass

    def _on_rois_updated_for_source(self, source_id: int) -> None:
        """Переопределяемый хук: оповестить рабочие потоки или внутренние компоненты о смене ROI."""
        try:
            # Попытка обновить в потоках, если они поддерживают соответствующий метод
            for t in getattr(self, 'detection_threads', []) or []:
                try:
                    if hasattr(t, 'set_rois_for_source'):
                        # Передадим текущие ROI для source_id в формате xywh
                        rois = self.get_rois_for_source(source_id)
                        t.set_rois_for_source(source_id, rois)
                    elif hasattr(t, 'roi'):
                        # Глобальное обновление
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

    def stop(self):
        self.run_flag = False
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
        self.stride = 1

    def reset_impl(self):
        pass

    def _process_impl(self):
        while self.run_flag:
            if not self.is_inited:
                sleep(0.01)
                continue

            image = self.queue_in.get()
            if not image:
                continue

            res, dropped_id = self.detection_threads[self.thread_counter].put(image, force=True)
            if dropped_id:
                self.queue_dropped_id.put(dropped_id)
            self.thread_counter += 1
            if self.thread_counter >= self.num_detection_threads:
                self.thread_counter = 0
