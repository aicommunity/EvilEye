from __future__ import annotations

import threading
import multiprocessing as _mp
from queue import Queue
from time import sleep
from typing import Any, Dict, List, Tuple

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame

EXEC_MODE_THREAD = "thread"
EXEC_MODE_PROCESS = "process"


@EvilEyeBase.register("RoiFeeder")
class RoiFeeder(EvilEyeBase):
    """Lightweight processor that extracts ROI crops from tracked objects

    Supports both thread and process execution modes via the
    ``execution_mode`` configuration parameter
    """

    ResultType = Frame

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.execution_mode = EXEC_MODE_THREAD

        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

        self.source_ids: List[int] = []
        self.padding: float = 0.0
        self.roi_size: Tuple[int, int] | None = None
        self.every_n_frames: int = 1

        self._frame_counters: Dict[int, int] = {}
        self._mp_control = None

        # Инъекции от Controller/ClassManager (явная инициализация вместо hasattr)
        self.class_mapping: dict = {}
        self.primary_by_id: list = []
        self.primary_by_name: list = []

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.padding = float(self.params.get('padding', 0.0))
        size = self.params.get('size', None)
        if isinstance(size, (list, tuple)) and len(size) == 2:
            self.roi_size = (int(size[0]), int(size[1]))
        self.every_n_frames = int(self.params.get('every_n_frames', 1))
        self.execution_mode = self.params.get('execution_mode', EXEC_MODE_THREAD)

    def get_params_impl(self):
        params: Dict[str, Any] = dict()
        params['source_ids'] = self.source_ids
        params['padding'] = self.padding
        params['size'] = list(self.roi_size) if self.roi_size else None
        params['every_n_frames'] = self.every_n_frames
        params['execution_mode'] = self.execution_mode
        return params

    def default(self):
        self.params.clear()
        self.source_ids = []
        self.padding = 0.0
        self.roi_size = None
        self.every_n_frames = 1

    def init_impl(self, **kwargs):
        if self.execution_mode == EXEC_MODE_PROCESS:
            self._init_process_mode()
        return True

    def _init_process_mode(self):
        from ..core.mp_control import MpControl
        from .mp_worker_attributes import MpWorkerRoiFeeder

        self._mp_control = MpControl(max_input_size=4, name="roi-feeder")
        worker = self._mp_control.add_worker(MpWorkerRoiFeeder)
        worker.set_params(self.params if self.params else {})
        self._mp_control.start()
        self.processing_thread = threading.Thread(
            target=self._process_dispatch_loop, daemon=True,
        )

    def release_impl(self):
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None

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
        self._frame_counters.clear()

    def put(self, input_data: tuple):
        if not self.queue_in.full():
            self.queue_in.put(input_data)
            return True
        else:
            try:
                _ = self.queue_in.get_nowait()
            except Exception:
                pass
            self.queue_in.put(input_data)
            return True

    def get(self):
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_source_ids(self) -> List[int]:
        return self.source_ids

    def start(self):
        self.run_flag = True
        if not self.processing_thread.is_alive():
            self.processing_thread.start()

    def stop(self):
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()
        if self._mp_control is not None:
            self._mp_control.stop()
            self._mp_control = None

    # -- Thread mode processing ------------------------------------------

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            data_pack = self.queue_in.get()
            if data_pack is None:
                continue

            (tracking_data, frame) = data_pack
            if frame.source_id not in self.source_ids:
                self.queue_out.put(data_pack)
                continue

            if frame.source_id not in self._frame_counters:
                self._frame_counters[frame.source_id] = 0
            self._frame_counters[frame.source_id] += 1

            if self._should_process_frame(frame.source_id):
                self._extract_rois(tracking_data, frame)

            self.queue_out.put(data_pack)

    # -- Process mode dispatch -------------------------------------------

    def _process_dispatch_loop(self):
        while self.run_flag:
            sleep(0.01)
            try:
                data_pack = self.queue_in.get(timeout=0.5)
            except Exception:
                continue
            if data_pack is None:
                continue
            try:
                self._mp_control.put(data_pack)
                result = self._mp_control.get(timeout=10.0)
                self.queue_out.put(result)
            except Exception as e:
                self.logger.error(f"Error in ROI feeder dispatch: {e}")
                self.queue_out.put(data_pack)

    # -- Helpers ---------------------------------------------------------

    def _should_process_frame(self, source_id: int) -> bool:
        if source_id not in self._frame_counters:
            return False
        return self._frame_counters[source_id] % self.every_n_frames == 0

    def _extract_rois(self, tracking_data, image):
        try:
            roi_data = []
            for track in tracking_data.tracks:
                roi_image = self._extract_roi_from_bbox(image.image, track.bounding_box)
                if roi_image is not None:
                    roi_data.append({
                        'track_id': track.track_id,
                        'roi_image': roi_image,
                        'bbox': track.bounding_box,
                        'class_id': track.class_id,
                    })
            if roi_data:
                tracking_data.roi_data = roi_data
        except Exception:
            pass

        except Exception as e:
            pass  # Silent error handling
    
    def _is_primary_object(self, track) -> bool:
        """Check if track represents a primary object"""
        # Check by class ID
        if track.class_id in self.primary_by_id:
            return True
        
        # Check by class name using class_mapping if available
        if self.class_mapping:
            for name, cid in self.class_mapping.items():
                if cid == track.class_id and name in self.primary_by_name:
                    return True
        else:
            # Fallback to hardcoded class names for backward compatibility
            class_names = ["person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck"]
            if track.class_id < len(class_names):
                class_name = class_names[track.class_id]
                if class_name in self.primary_by_name:
                    return True
        
        return False
    
    def _extract_roi_from_bbox(self, image, bbox):
        """Extract ROI image from bounding box with padding."""
        try:
            x1, y1, x2, y2 = bbox
            h, w = image.shape[:2]
            pad_x = int((x2 - x1) * self.padding)
            pad_y = int((y2 - y1) * self.padding)
            x1_pad = max(0, int(x1 - pad_x))
            y1_pad = max(0, int(y1 - pad_y))
            x2_pad = min(w, int(x2 + pad_x))
            y2_pad = min(h, int(y2 + pad_y))
            roi = image[y1_pad:y2_pad, x1_pad:x2_pad]
            if roi.size == 0:
                return None
            return roi
        except Exception as e:
            self.logger.error(f"Error extracting ROI from bbox: {e}")
            return None
