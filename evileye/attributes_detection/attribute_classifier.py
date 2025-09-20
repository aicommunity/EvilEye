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
        self.attribute_detector = None
        
        # Threading components
        self.run_flag = False
        self.queue_in = Queue(maxsize=2)
        self.queue_out = Queue()
        self.processing_thread = threading.Thread(target=self._process_impl)

    def set_params_impl(self):
        """Set parameters from configuration"""
        self.enabled = self.params.get('enabled', True)
        
        # Initialize AttributeDetector with parameters
        if self.attribute_detector is None:
            self.attribute_detector = AttributeDetector()
        
        # Set parameters for AttributeDetector
        detector_params = {
            'model': self.params.get('model', 'models/y8mhardhats.pt'),
            'attrs': self.params.get('attrs', ['hard_hat', 'no_hard_hat']),
            'confidence_thresholds': self.params.get('confidence_thresholds', {}),
            'source_ids': self.params.get('source_ids', [0]),
            'stride': self.params.get('stride', 1),
            'roi': [[]],
            'num_detection_threads': 1
        }
        
        self.attribute_detector.params = detector_params
        self.attribute_detector.set_params_impl()

    def get_params_impl(self):
        """Get current parameters"""
        params = super().get_params_impl()
        params['enabled'] = self.enabled
        if self.attribute_detector:
            detector_params = self.attribute_detector.get_params_impl()
            params.update(detector_params)
        return params

    def init_impl(self, **kwargs):
        """Initialize attribute detector"""
        if not self.enabled:
            return True
            
        try:
            if self.attribute_detector:
                success = self.attribute_detector.init_impl(**kwargs)
                if success:
                    print(f"✅ AttributeClassifier initialized with AttributeDetector")
                return success
            return False
        except Exception as e:
            print(f"❌ Failed to initialize AttributeClassifier: {e}")
            return False

    def release_impl(self):
        if self.attribute_detector:
            self.attribute_detector.release_impl()

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
            frame = self.queue_in.get()
            if frame is None:
                continue
                
            # Skip processing if not enabled or no detector
            if not self.enabled or self.attribute_detector is None:
                self.queue_out.put(frame)
                continue
                
            # Check if frame has ROI data from RoiFeeder
            if hasattr(frame, 'roi_data') and frame.roi_data:
                print(f"🔍 AttributeClassifier: Processing {len(frame.roi_data)} ROIs")
                try:
                    # Process each ROI using AttributeDetector
                    for roi_info in frame.roi_data:
                        track_id = roi_info.get('track_id')
                        roi_image = roi_info.get('roi_image')
                        bbox = roi_info.get('bbox')
                        
                        print(f"🔍 AttributeClassifier: Processing ROI for track {track_id}, bbox {bbox}, shape {roi_image.shape if roi_image is not None else 'None'}")
                        
                        if roi_image is not None and track_id is not None:
                            # Use AttributeDetector to classify ROI
                            attr_results = self._classify_roi_with_detector(roi_image)
                            
                            # Store results in frame for ObjectsHandler
                            if not hasattr(frame, 'attr_results'):
                                frame.attr_results = {}
                            frame.attr_results[track_id] = attr_results
                            
                except Exception as e:
                    print(f"❌ Error processing ROI in AttributeClassifier: {e}")
            else:
                print("🔍 AttributeClassifier: No ROI data in frame")
            
            # Always pass frame through
            self.queue_out.put(frame)
    
    def _classify_roi_with_detector(self, roi_image: np.ndarray) -> Dict[str, Dict[str, Any]]:
        """Classify attributes in ROI image using AttributeDetector"""
        if self.attribute_detector is None:
            print("🔍 AttributeClassifier: No attribute detector available")
            return {}
            
        try:
            print(f"🔍 AttributeClassifier: Classifying ROI image shape {roi_image.shape}")
            # Create a mock CaptureImage for the detector
            from ..core.frame import CaptureImage
            mock_image = CaptureImage()
            mock_image.image = roi_image
            mock_image.source_id = 0
            mock_image.frame_id = 0
            
            # Put image into detector
            print("🔍 AttributeClassifier: Putting image into detector")
            self.attribute_detector.put(mock_image)
            
            # Get detection results
            print("🔍 AttributeClassifier: Getting detection results")
            detection_results = self.attribute_detector.get()
            
            if detection_results is None:
                print("🔍 AttributeClassifier: No detection results")
                return {}
            
            print(f"🔍 AttributeClassifier: Got {len(detection_results.detections)} detections")
            
            # Convert detection results to attribute results format
            attr_results = {}
            for detection in detection_results.detections:
                class_id = int(detection.class_id)
                confidence = float(detection.confidence)
                
                # Map class_id to attribute name
                attr_name = None
                for attr_id, attr_name_mapped in self.attribute_detector.detection_threads[0].attr_class_mapping.items():
                    if attr_id == class_id:
                        attr_name = attr_name_mapped
                        break
                
                if attr_name:
                    threshold = self.attribute_detector.conf_thresholds.get(attr_name, 0.5)
                    attr_results[attr_name] = {
                        'detected_now': confidence >= threshold,
                        'confidence': confidence,
                        'max_confidence': confidence,
                        'detection_count': 1
                    }
                    print(f"🔍 AttributeDetection: {attr_name} - conf {confidence:.3f}")
            
            return attr_results
            
        except Exception as e:
            print(f"❌ Error in ROI classification with detector: {e}")
            return {}

    def get_source_ids(self):
        """Get source IDs for this processor"""
        return self.params.get('source_ids', [0])

    def put(self, frame: Frame) -> bool:
        """Put frame into processing queue"""
        if not self.queue_in.full():
            self.queue_in.put(frame)
            return True
        return False

    def get(self) -> Frame | None:
        """Get processed frame from output queue"""
        if self.queue_out.empty():
            return None
        return self.queue_out.get()

    def default(self):
        """Default implementation"""
        self.params.clear()