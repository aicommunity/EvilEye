from __future__ import annotations

import threading
from queue import Queue
from time import sleep
from typing import Any, Dict
import numpy as np

from ..core.base_class import EvilEyeBase

EXEC_MODE_THREAD = "thread"
EXEC_MODE_PROCESS = "process"


@EvilEyeBase.register("AttributeClassifier")
class AttributeClassifier(EvilEyeBase):
    """Attribute classifier that runs YOLO inference on ROI crops

    Supports both thread and process execution modes via the
    ``execution_mode`` configuration parameter
    """

    def __init__(self):
        super().__init__()
        self.enabled = True
        self.execution_mode = EXEC_MODE_THREAD

        self.yolo_model = None
        self.model_path = 'models/yolo11n.pt'
        self.attrs = []
        self.attr_class_mapping = {}
        self.conf_threshold = 0.5
        self.inference_size = 224

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.queue_dropped_id = Queue()
        self.processing_thread = None

        self._mp_control = None

    def set_params_impl(self):
        self.enabled = self.params.get('enabled', True)
        self.execution_mode = self.params.get('execution_mode', EXEC_MODE_THREAD)

        if self.enabled:
            self.model_path = self.params.get('model', 'models/yolo11n.pt')
            self.attrs = self.params.get('attrs', [])
            self.conf_threshold = self.params.get('conf_threshold', 0.5)
            self.inference_size = self.params.get('inference_size', 224)

            class_mapping = self.params.get('class_mapping', {})
            if not class_mapping:
                for i, attr_name in enumerate(self.attrs):
                    self.attr_class_mapping[i] = attr_name
            else:
                for attr_name, class_id in class_mapping.items():
                    if attr_name in self.attrs:
                        self.attr_class_mapping[class_id] = attr_name

    def get_params_impl(self):
        params = super().get_params_impl()
        params['enabled'] = self.enabled
        params['model'] = getattr(self, 'model_path', 'models/yolo11n.pt')
        params['attrs'] = getattr(self, 'attrs', [])
        params['conf_threshold'] = getattr(self, 'conf_threshold', 0.5)
        params['inference_size'] = getattr(self, 'inference_size', 224)
        params['execution_mode'] = self.execution_mode
        return params

    def init_impl(self, **kwargs):
        if not self.enabled:
            return True

        if self.execution_mode == EXEC_MODE_PROCESS:
            return self._init_process_mode()
        return self._init_thread_mode()

    def _init_thread_mode(self):
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO(self.model_path)
            self.yolo_model.fuse()
            self.logger.info(f"AttributeClassifier initialized with YOLO model: {self.model_path}")
            self.processing_thread = threading.Thread(target=self._process_impl)
            return True
        except Exception as e:
            self.logger.info(f"Failed to initialize AttributeClassifier: {e}")
            return False

    def _init_process_mode(self):
        from ..core.mp_control import MpControl
        from .mp_worker_attributes import MpWorkerAttributeClassifier

        self._mp_control = MpControl(max_input_size=4, name="attr-classifier")
        worker = self._mp_control.add_worker(MpWorkerAttributeClassifier)
        worker.set_params(self.params if self.params else {})
        self._mp_control.start()
        self.processing_thread = threading.Thread(
            target=self._process_dispatch_loop, daemon=True,
        )
        self.logger.info("AttributeClassifier initialized in PROCESS mode")
        return True

    def release_impl(self):
        if self.yolo_model:
            del self.yolo_model
            self.yolo_model = None
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None
        if self.processing_thread is not None:
            del self.processing_thread
            self.processing_thread = None

    def reset_impl(self):
        while not self.queue_in.empty():
            try:
                self.queue_in.get_nowait()
            except Exception:
                break
        while not self.queue_out.empty():
            try:
                self.queue_out.get_nowait()
            except Exception:
                break

    def start(self):
        if not self.run_flag:
            self.run_flag = True
            if self.processing_thread and not self.processing_thread.is_alive():
                self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread and self.processing_thread.is_alive():
            self.processing_thread.join()
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None

    # -- Thread mode processing ------------------------------------------

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            detections = self.queue_in.get()
            if detections is None:
                continue

            if not self.enabled or self.yolo_model is None:
                self.queue_out.put(detections)
                continue

            tracking_data, frame = detections

            if hasattr(tracking_data, 'roi_data') and tracking_data.roi_data:
                try:
                    for roi_info in tracking_data.roi_data:
                        track_id = roi_info.get('track_id')
                        roi_image = roi_info.get('roi_image')
                        if roi_image is not None and track_id is not None:
                            attr_results = self._classify_roi_with_detector(roi_image)
                            if not hasattr(tracking_data, 'attr_results'):
                                tracking_data.attr_results = {}
                            tracking_data.attr_results[track_id] = attr_results
                except Exception:
                    pass

            self.queue_out.put((tracking_data, frame))

    # -- Process mode dispatch -------------------------------------------

    def _process_dispatch_loop(self):
        while self.run_flag:
            sleep(0.01)
            try:
                detections = self.queue_in.get(timeout=0.5)
            except Exception:
                continue
            if detections is None:
                continue
            try:
                self._mp_control.put(detections)
                result = self._mp_control.get(timeout=10.0)
                self.queue_out.put(result)
            except Exception as e:
                self.logger.error(f"Error in attribute classifier dispatch: {e}")
                self.queue_out.put(detections)

    # -- Direct YOLO classification (thread mode) ------------------------

    def _classify_roi_with_detector(self, roi_image: np.ndarray) -> Dict[str, Dict[str, Any]]:
        if self.yolo_model is None:
            return {}
        try:
            results = self.yolo_model.predict(
                source=roi_image,
                classes=list(self.attr_class_mapping.keys()),
                verbose=False,
                conf=self.conf_threshold,
                imgsz=self.inference_size,
            )
            if not results or len(results) == 0:
                return {}
            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                return {n: {'detected_now': False, 'confidence': 0.0} for n in self.attrs}

            attr_results = {n: {'detected_now': False, 'confidence': 0.0} for n in self.attrs}
            boxes = result.boxes.cpu().numpy()
            for box in boxes:
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                attr_name = self.attr_class_mapping.get(class_id)
                if attr_name and confidence >= self.conf_threshold:
                    attr_results[attr_name] = {
                        'detected_now': True,
                        'confidence': confidence,
                        'bbox': bbox,
                        'class_id': class_id,
                    }
            return attr_results
        except Exception:
            return {}

    def get_source_ids(self):
        return self.params.get('source_ids', [0])

    def put(self, det_info, force=False):
        dropped_id = []
        result = True
        if self.queue_in.full():
            if force:
                dropped_data = self.queue_in.get()
                dropped_id.append(dropped_data[1].source_id)
                dropped_id.append(dropped_data[1].frame_id)
            else:
                dropped_id.append(det_info[1].source_id)
                dropped_id.append(det_info[1].frame_id)
                result = False
        if len(dropped_id) > 0:
            self.queue_dropped_id.put(dropped_id)
        if result:
            self.queue_in.put(det_info)
        return result

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_dropped_ids(self) -> list:
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_oueue_out_size(self):
        return self.queue_out.qsize()

    def default(self):
        self.params.clear()
