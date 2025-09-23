from __future__ import annotations

import threading
from queue import Queue
from time import sleep
from typing import Any, Dict, List, Tuple

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame


@EvilEyeBase.register("RoiFeeder")
class RoiFeeder(EvilEyeBase):
    """
    Лёгкий процессор для подготовки ROI по bbox первичных объектов.
    На первом этапе реализует pass-through, сохраняя интерфейс ProcessorFrame.

    Требуемый интерфейс для ProcessorFrame:
    - put(frame: Frame) -> bool
    - get() -> Frame | None
    - get_source_ids() -> List[int]
    - start()/stop()
    """

    ResultType = Frame

    def __init__(self):
        super().__init__()

        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

        # Конфигурируемые параметры
        self.source_ids: List[int] = []
        self.padding: float = 0.0
        self.roi_size: Tuple[int, int] | None = None  # (w, h)
        self.every_n_frames: int = 1

        # Внутренняя книга учёта частоты
        self._frame_counters = {}  # Dict[int, int]

    def set_params_impl(self):
        self.source_ids = self.params.get('source_ids', [])
        self.padding = float(self.params.get('padding', 0.0))
        size = self.params.get('size', None)
        if isinstance(size, (list, tuple)) and len(size) == 2:
            self.roi_size = (int(size[0]), int(size[1]))
        self.every_n_frames = int(self.params.get('every_n_frames', 1))

    def get_params_impl(self):
        params: Dict[str, Any] = dict()
        params['source_ids'] = self.source_ids
        params['padding'] = self.padding
        params['size'] = list(self.roi_size) if self.roi_size else None
        params['every_n_frames'] = self.every_n_frames
        return params

    def default(self):
        self.params.clear()
        self.source_ids = []
        self.padding = 0.0
        self.roi_size = None
        self.every_n_frames = 1

    def init_impl(self, **kwargs):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        # Очистка очередей
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

    def _process_impl(self):
        while self.run_flag:
            sleep(0.01)
            data_pack = self.queue_in.get()
            if data_pack is None:
                continue

            (tracking_data, frame) = data_pack
            # Check if we should process this data_pack
            if frame.source_id not in self.source_ids:
                # Pass data_pack through even if source_id doesn't match
                self.queue_out.put(data_pack)
                continue
                
            # Increment data_pack counter for this source
            if frame.source_id not in self._frame_counters:
                self._frame_counters[frame.source_id] = 0
            self._frame_counters[frame.source_id] += 1
            
            # Extract ROI from primary objects if conditions are met
            if self._should_process_frame(frame.source_id):
                self._extract_rois(tracking_data, frame)
            
            # Always pass data_pack through
            self.queue_out.put(data_pack)
    
    def _should_process_frame(self, source_id: int) -> bool:
        """Check if frame should be processed based on every_n_frames setting"""
        if source_id not in self._frame_counters:
            return False
        return self._frame_counters[source_id] % self.every_n_frames == 0
    
    def _extract_rois(self, tracking_data, image):
        """Extract ROI images from primary objects in the frame"""
        try:
            # Get tracking results from frame (if available)
            roi_data = []

            for track in tracking_data.tracks:
                # Extract ROI from bounding box
                roi_image = self._extract_roi_from_bbox(image.image, track.bounding_box)
                if roi_image is not None:
                    roi_data.append({
                        'track_id': track.track_id,
                        'roi_image': roi_image,
                        'bbox': track.bounding_box,
                        'class_id': track.class_id
                    })

            # Store ROI data in frame
            if roi_data:
                tracking_data.roi_data = roi_data

        except Exception as e:
            pass  # Silent error handling
    
    def _is_primary_object(self, track) -> bool:
        """Check if track represents a primary object"""
        # Check by class ID
        if track.class_id in self.primary_by_id:
            return True
        
        # Check by class name using class_mapping if available
        if hasattr(self, 'class_mapping') and self.class_mapping:
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
    
    def _extract_roi_from_bbox(self, image: np.ndarray, bbox) -> np.ndarray | None:
        """Extract ROI image from bounding box with padding"""
        try:
            x1, y1, x2, y2 = bbox
            
            # Add padding
            h, w = image.shape[:2]
            pad_x = int((x2 - x1) * self.padding)
            pad_y = int((y2 - y1) * self.padding)
            
            # Calculate padded coordinates
            x1_pad = max(0, int(x1 - pad_x))
            y1_pad = max(0, int(y1 - pad_y))
            x2_pad = min(w, int(x2 + pad_x))
            y2_pad = min(h, int(y2 + pad_y))
            
            # Extract ROI
            roi = image[y1_pad:y2_pad, x1_pad:x2_pad]
            
            if roi.size == 0:
                return None
            
            # Resize to target size
            #roi_resized = cv2.resize(roi, self.target_size)
            
            return roi
            
        except Exception as e:
            self.logger.error(f"Error extracting ROI from bbox: {e}")
            return None


