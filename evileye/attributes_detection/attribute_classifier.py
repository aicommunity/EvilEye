from __future__ import annotations

import threading
from queue import Queue
from time import sleep
from typing import Any, Dict, List, Tuple
import cv2
import numpy as np

from ..core.base_class import EvilEyeBase
from ..core.frame import Frame
from .attribute_detector import AttributeDetector


@EvilEyeBase.register("AttributeClassifier")
class AttributeClassifier(EvilEyeBase):
    """
    Attribute classifier wrapper that uses AttributeDetector for ROI classification.
    Processes ROI images from RoiFeeder and returns attribute detection results.
    
    Interface for ProcessorFrame:
    - put(frame: Frame) -> bool
    - get() -> Frame | None
    - get_source_ids() -> List[int]
    - start()/stop()
    """
    
    def __init__(self):
        super().__init__()
        self.enabled = True
        
        # Direct YOLO model instead of AttributeDetector
        self.yolo_model = None
        self.attr_class_mapping = {}
        self.conf_threshold = 0.5
        self.inference_size = 224
        
        # Threading components
        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.queue_dropped_id = Queue()
        self.processing_thread = None

    def set_params_impl(self):
        """Set parameters from configuration"""
        self.enabled = self.params.get('enabled', True)
        
        if self.enabled:
            # Set YOLO model parameters
            self.model_path = self.params.get('model', 'models/yolo11n.pt')
            self.attrs = self.params.get('attrs', [])
            self.conf_threshold = self.params.get('conf_threshold', 0.5)
            self.inference_size = self.params.get('inference_size', 224)
            
            # Create class mapping from configuration
            # Get class mapping from config or use default sequential mapping
            class_mapping = self.params.get('class_mapping', {})
            if not class_mapping:
                # If no class mapping provided, create sequential mapping (0, 1, 2, ...)
                for i, attr_name in enumerate(self.attrs):
                    self.attr_class_mapping[i] = attr_name
            else:
                # Use provided class mapping
                for attr_name, class_id in class_mapping.items():
                    if attr_name in self.attrs:
                        self.attr_class_mapping[class_id] = attr_name

    def get_params_impl(self):
        """Get current parameters"""
        params = super().get_params_impl()
        params['enabled'] = self.enabled
        params['model'] = getattr(self, 'model_path', 'models/yolo11n.pt')
        params['attrs'] = getattr(self, 'attrs', [])
        params['conf_threshold'] = getattr(self, 'conf_threshold', 0.5)
        params['inference_size'] = getattr(self, 'inference_size', 224)
        return params

    def init_impl(self, **kwargs):
        """Initialize YOLO model directly"""
        if not self.enabled:
            return True
            
        try:
            from ultralytics import YOLO
            self.yolo_model = YOLO(self.model_path)
            self.yolo_model.fuse()  # Fuse Conv+BN layers for faster inference
            self.logger.info(f"AttributeClassifier initialized with YOLO model: {self.model_path}")
            self.logger.info(f"Attribute classes: {self.attr_class_mapping}")
            self.processing_thread = threading.Thread(target=self._process_impl)
            return True
        except Exception as e:
            self.logger.info(f"Failed to initialize AttributeClassifier: {e}")
            return False

    def release_impl(self):
        if self.yolo_model:
            del self.yolo_model
            self.yolo_model = None
        del self.processing_thread
        self.processing_thread = None

    def reset_impl(self):
        while not self.queue_in.empty():
            try:
                self.queue_in.get_nowait()
            except:
                break
        while not self.queue_out.empty():
            try:
                self.queue_out.get_nowait()
            except:
                break
        if self.attribute_detector:
            self.attribute_detector.reset_impl()

    def start(self):
        """Start the processing thread"""
        if not self.run_flag:
            self.run_flag = True
            if not self.processing_thread.is_alive():
                self.processing_thread.start()

    def stop(self):
        """Stop the processing thread"""
        self.run_flag = False
        self.queue_in.put(None)
        if self.processing_thread.is_alive():
            self.processing_thread.join()

    def _process_impl(self):
        """Process frames and classify attributes in ROI images"""
        while self.run_flag:
            sleep(0.01)
            detections = self.queue_in.get()
            if detections is None:
                continue
                
            # Skip processing if not enabled or no YOLO model
            if not self.enabled or self.yolo_model is None:
                self.queue_out.put(detections)
                continue
                
            # Unpack data from RoiFeeder: (tracking_data, frame)
            tracking_data, frame = detections
                
            # Check if tracking_data has ROI data from RoiFeeder
            if hasattr(tracking_data, 'roi_data') and tracking_data.roi_data:
                try:
                    # Process each ROI using AttributeDetector
                    for roi_info in tracking_data.roi_data:
                        track_id = roi_info.get('track_id')
                        roi_image = roi_info.get('roi_image')
                        bbox = roi_info.get('bbox')
                        
                        if roi_image is not None and track_id is not None:
                            # Use AttributeDetector to classify ROI
                            attr_results = self._classify_roi_with_detector(roi_image)
                            
                            # Store results in tracking_data for ObjectsHandler
                            if not hasattr(tracking_data, 'attr_results'):
                                tracking_data.attr_results = {}
                            tracking_data.attr_results[track_id] = attr_results
                            
                except Exception as e:
                    pass  # Silent error handling
            
            # Always pass detections through: (tracking_data, frame)
            self.queue_out.put((tracking_data, frame))
    
    def _classify_roi_with_detector(self, roi_image: np.ndarray) -> Dict[str, Dict[str, Any]]:
        """Classify attributes in ROI image using direct YOLO call"""
        if self.yolo_model is None:
            return {}
            
        try:
            # Direct YOLO inference
            results = self.yolo_model.predict(
                source=roi_image,
                classes=list(self.attr_class_mapping.keys()),
                verbose=False,
                conf=self.conf_threshold,
                imgsz=self.inference_size
            )
            
            if not results or len(results) == 0:
                return {}
            
            result = results[0]
            if result.boxes is None or len(result.boxes) == 0:
                # No detections - return all attributes as not detected
                attr_results = {}
                for attr_name in self.attrs:
                    attr_results[attr_name] = {
                        'detected_now': False,
                        'confidence': 0.0,
                        'max_confidence': 0.0,
                        'detection_count': 0,
                        'bbox': None,
                        'class_id': None
                    }
                return attr_results
            
            # Process YOLO results
            attr_results = {}
            boxes = result.boxes.cpu().numpy()
            
            # Initialize all configured attributes as not detected
            for attr_name in self.attrs:
                attr_results[attr_name] = {
                    'detected_now': False,
                    'confidence': 0.0,
                    'max_confidence': 0.0,
                    'detection_count': 0,
                    'bbox': None,
                    'class_id': None
                }
            
            # Update with actual detections
            for i, box in enumerate(boxes):
                class_id = int(box.cls[0])
                confidence = float(box.conf[0])
                bbox = box.xyxy[0].tolist()
                
                # Map class_id to attribute name
                attr_name = self.attr_class_mapping.get(class_id)
                if attr_name and confidence >= self.conf_threshold:
                    attr_results[attr_name] = {
                        'detected_now': True,
                        'confidence': confidence,
                        'max_confidence': confidence,
                        'detection_count': 1,
                        'bbox': bbox,
                        'class_id': class_id
                    }
            
            return attr_results
            
        except Exception as e:
            return {}

    def get_source_ids(self):
        """Get source IDs for this processor"""
        return self.params.get('source_ids', [0])

    def put(self, det_info, force=False):
        """Put detection info into processing queue"""
        dropped_id = []
        result = True
        if self.queue_in.full():
            if force:
                dropped_data = self.queue_in.get()
                dropped_id.append(dropped_data[1].source_id)
                dropped_id.append(dropped_data[1].frame_id)
                result = True
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
        """Get processed results from output queue"""
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def get_dropped_ids(self) -> list:
        """Get dropped frame IDs"""
        res = []
        while not self.queue_dropped_id.empty():
            res.append(self.queue_dropped_id.get())
        return res

    def get_oueue_out_size(self):
        """Get output queue size"""
        return self.queue_out.qsize()

    def default(self):
        """Default implementation"""
        self.params.clear()