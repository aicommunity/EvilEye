from queue import Queue
import threading
from ultralytics import YOLO
from ..object_detector.detection_thread_base import DetectionThreadBase
from typing import Dict, Any, List
import numpy as np
from ..core.logger import get_module_logger


class AttributeDetectionThread(DetectionThreadBase):
    """Thread for attribute detection using YOLO model on ROI images"""
    
    def __init__(self, model_name: str, stride: int, classes: list, source_ids: list, roi: list, inf_params: dict, queue_out: Queue):
        self.logger = get_module_logger("attribute_detection_thread")
        self.model_name = model_name
        self.model = None
        self.attr_class_mapping = {}
        self.conf_thresholds = {}
        super().__init__(stride, classes, source_ids, roi, inf_params, queue_out)

    def init_detection_implementation(self):
        """Initialize YOLO model for attribute classification"""
        if self.model is None:
            self.model = YOLO(self.model_name)
            self.model.fuse()  # Fuse Conv+BN layers for faster inference
            
            # Create class mapping for COCO classes
            # For yolo11n.pt: person=0, bottle=39
            self.attr_class_mapping = {}
            coco_class_mapping = {
                "person": 0,
                "bottle": 39
            }
            for attr_name in self.classes:
                if attr_name in coco_class_mapping:
                    self.attr_class_mapping[coco_class_mapping[attr_name]] = attr_name
                
            self.logger.info(f"AttributeDetectionThread initialized with model: {self.model_name}")
            self.logger.info(f"Attribute classes: {self.attr_class_mapping}")
            self.logger.info(f"COCO class mapping: {coco_class_mapping}")

    def predict(self, images: list):
        """Run YOLO inference on ROI images"""
        # Filter out None images before passing to model
        if not isinstance(images, list):
            self.logger.warning(f"Expected list of images, got {type(images)}")
            return None
        
        # Track which images are None to map results back correctly
        valid_images = []
        image_indices = []  # Track original indices of valid images
        for i, img in enumerate(images):
            if img is not None:
                valid_images.append(img)
                image_indices.append(i)
        
        # If all images are None, return None results
        if len(valid_images) == 0:
            self.logger.warning("All images are None, cannot perform prediction")
            return [None] * len(images)
        
        try:
            results = self.model.predict(source=valid_images, classes=list(self.attr_class_mapping.keys()), verbose=False, **self.inf_params)
            
            # Map results back to original positions (None for invalid images)
            if results is None:
                return [None] * len(images)
            
            # Convert results to list if needed
            if not isinstance(results, list):
                results = [results]
            
            # Create result list with None for invalid images
            full_results = [None] * len(images)
            for idx, result_idx in enumerate(image_indices):
                if idx < len(results):
                    full_results[result_idx] = results[idx]
            
            return full_results
        except Exception as e:
            self.logger.error(f"Error during attribute detection model prediction: {e}")
            self.logger.debug("Prediction error details", exc_info=True)
            return [None] * len(images)

    def get_bboxes(self, result, roi):
        """Process YOLO results and return attribute detections"""
        bboxes_coords = []
        confidences = []
        ids = []
        boxes = result.boxes.cpu().numpy()
        coords = boxes.xyxy
        confs = boxes.conf
        class_ids = boxes.cls
        
        for coord, class_id, conf in zip(coords, class_ids, confs):
            class_id_int = int(class_id)
            if class_id_int not in self.attr_class_mapping:
                continue
            
            attr_name = self.attr_class_mapping[class_id_int]
            
            # For attribute detection, we don't need coordinate transformation
            # as we're working with ROI images directly
            bboxes_coords.append(coord)
            confidences.append(conf)
            ids.append(class_id)
        
        return bboxes_coords, confidences, ids

    def set_confidence_thresholds(self, thresholds: Dict[str, float]):
        """Set confidence thresholds for each attribute"""
        self.conf_thresholds = thresholds
