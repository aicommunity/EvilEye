from __future__ import annotations

from abc import ABC, abstractmethod
from queue import Queue
import threading
from time import sleep
from typing import Optional

from ..core.base_class import EvilEyeBase
from ..core.class_manager import ClassManager
from ..core.frame import CaptureImage

from ..core.mp_queue_config import (
    detector_input_queue_size,
    detector_output_queue_size,
)
from .constants import (
    DEFAULT_NUM_DETECTION_THREADS,
    DEFAULT_STRIDE,
    MODEL_PRELOAD_TIMEOUT,
    MODEL_READY_TIMEOUT,
    PROCESSING_SLEEP_INTERVAL,
    THREAD_START_DELAY,
)

# Execution mode constants
from ..core.processor_base import (
    DEFAULT_EXECUTION_MODE,
    EXEC_MODE_PROCESS,
    EXEC_MODE_THREAD,
)


class DetectionResult:
    def __init__(self):
        self.bounding_box = []
        self.confidence = 0.0
        self.class_id = None
        self.detection_data = dict()


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
        self.execution_mode = DEFAULT_EXECUTION_MODE
        self.queue_in = None
        # IMPORTANT: output queue must stay bounded, otherwise if downstream is slower
        # (e.g. controller/visualizer lag), results accumulate and memory grows unbounded.
        # We only need the latest results.
        self.queue_out = None
        self.queue_dropped_id = None
        self._init_queues()
        self.source_ids = []
        self.classes = []
        self.stride = DEFAULT_STRIDE
        self.roi = [[]]

        self.num_detection_threads = DEFAULT_NUM_DETECTION_THREADS
        self.detection_threads = []
        self.thread_counter = 0

        self.processing_thread = None

        # Multiprocessing pool (used when execution_mode == "process")
        self._mp_control = None

        self.model_class_mapping = None
        self._model_class_mapping_cache: Optional[dict] = None
        self.class_manager = None  # Will be set by Controller
        self._roi_cache: dict[int, list[list[int]]] = {}

    def _init_queues(self):
        """Create queues matching current execution_mode."""
        # Detector dispatcher and pipeline run in the same process.
        # Keep these queues thread-local even in process execution_mode;
        # true multiprocessing boundary is inside DetectionThreadYoloMp/MpControl.
        # This avoids unnecessary pickle/IPC overhead on hot path.
        self.queue_in = Queue(maxsize=detector_input_queue_size())
        self.queue_out = Queue(maxsize=detector_output_queue_size())
        self.queue_dropped_id = Queue()

    def put(self, image: CaptureImage) -> bool:
        """Put image into input queue for processing."""
        try:
            self.queue_in.put_nowait(image)
            return True
        except Exception:
            try:
                dropped_image = self.queue_in.get_nowait()
            except Exception:
                dropped_image = None

            try:
                self.queue_in.put_nowait(image)
                if dropped_image is not None:
                    try:
                        self.queue_dropped_id.put_nowait(
                            [dropped_image.source_id, dropped_image.frame_id]
                        )
                    except Exception:
                        pass
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
                self.logger.debug(f"Auto-updated model_class_mapping from detection thread: {model_class_mapping}")

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
                self.logger.debug(f"Classes updated from {original_classes} to {self.classes} using ClassManager")
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
                    self.logger.warning(
                        f"Warning: Class names provided but model_class_mapping unavailable yet: {self.classes}")
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
                self.logger.debug(f"Classes updated from {original_classes} to {self.classes} using model mapping")

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

        self.logger.debug(f"Updating classes after model loading. Original: {original_classes}")

        # Re-process classes with now-available model_class_mapping
        if all(isinstance(cls, str) for cls in original_classes):
            # Classes are names - convert to IDs using model_class_mapping
            new_classes = [self.model_class_mapping.get(name, -1) for name in original_classes]
            new_classes = [cls_id for cls_id in new_classes if cls_id != -1]

            if new_classes != self.classes:
                self.logger.debug(f"Classes updated from {self.classes} to {new_classes} using model mapping")
                self.classes = new_classes

                # Update classes in all detection threads
                self._update_threads_classes()
            else:
                self.logger.debug(f"Classes already correct: {self.classes}")
        else:
            self.logger.debug(f"Classes are IDs, conversion not needed: {self.classes}")

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
                self.logger.debug(f"Late update: classes from {self.classes} to {new_classes} using model mapping")
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

        new_mode = self.params.get('execution_mode', DEFAULT_EXECUTION_MODE)
        if new_mode != self.execution_mode:
            self.execution_mode = new_mode
            self._init_queues()
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
        params['execution_mode'] = self.execution_mode
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
        # Короткая пауза, чтобы рабочие потоки успели стартовать; модели
        # инициализируются строго внутри detection-потоков в init_detection_implementation(),
        # перед первым predict, что важно для корректной работы ultralytics.
        import time
        time.sleep(MODEL_PRELOAD_TIMEOUT)

    def is_ready(self, timeout: float = MODEL_READY_TIMEOUT) -> bool:
        """
        Check if detector is ready to process frames (models loaded).
        Returns True if all detection threads have loaded their models.
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
            all_ready = True
            for thread in self.detection_threads:
                mp_control = getattr(thread, "mp_control", None)
                if mp_control is not None:
                    if mp_control.is_alive():
                        continue
                    all_ready = False
                    break
                if not hasattr(thread, "model") or thread.model is None:
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
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join(timeout=2.0)
            if self.processing_thread.is_alive():
                self.logger.warning("Detection processing_thread did not stop within 2s")
        # Stop multiprocessing pool if active
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        self.logger.info('Detection stopped')

    def init_impl(self):
        if self.execution_mode == EXEC_MODE_PROCESS:
            # In process mode the dispatcher runs as a thread that reads
            # from queue_in and distributes work to child processes
            self.processing_thread = threading.Thread(target=self._process_impl)
        else:
            self.processing_thread = threading.Thread(target=self._process_impl)

    def release_impl(self):
        for i in range(len(self.detection_threads)):
            self.detection_threads[i].stop()

        self.detection_threads = []
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        if self.processing_thread is not None:
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
            thread.start()
            self.detection_threads.append(thread)
        return True

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

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info["model_name"] = self.model_name

    def default(self):
        super().default()
        self.model_name = None
        self.params.clear()

    def _process_impl(self):
        """Main processing loop that distributes images to detection threads."""
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

            res, dropped_id = self.detection_threads[self.thread_counter].put(image, force=True)
            if dropped_id:
                try:
                    self.queue_dropped_id.put_nowait(dropped_id)
                except Exception:
                    pass
            self.thread_counter += 1
            if self.thread_counter >= self.num_detection_threads:
                self.thread_counter = 0
