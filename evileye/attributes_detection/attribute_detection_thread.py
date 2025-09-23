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
        results = self.model.predict(source=images, classes=list(self.attr_class_mapping.keys()), verbose=False, **self.inf_params)
        return results

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
