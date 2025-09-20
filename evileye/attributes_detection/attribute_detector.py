import os
from ..object_detector.object_detection_base import ObjectDetectorBase
from .attribute_detection_thread import AttributeDetectionThread
from ..core.base_class import EvilEyeBase
from typing import Dict, Any, List
import numpy as np


@EvilEyeBase.register("AttributeDetector")
class AttributeDetector(ObjectDetectorBase):
    """Attribute detector for ROI images using YOLO model"""
    
    def __init__(self):
        super().__init__()
        self.model_name = "models/y8mhardhats.pt"
        self.attrs = ["hard_hat", "no_hard_hat"]
        self.conf_thresholds = {}

    def init_impl(self):
        """Initialize attribute detection threads"""
        super().init_impl()
        self.detection_threads = []
        inf_params = {
            "show": self.params.get('show', False), 
            'conf': self.params.get('conf', 0.1),
            'save': self.params.get('save', False), 
            "imgsz": self.params.get('inference_size', 224),
            "device": self.params.get('device', None)
        }

        for i in range(self.num_detection_threads):
            # Resolve relative model path to current working directory for access
            model_path = self.model_name
            if not os.path.isabs(model_path):
                model_path = os.path.join(os.getcwd(), model_path)
            
            try:
                thread = AttributeDetectionThread(
                    model_path, self.stride, self.attrs, self.source_ids, self.roi, inf_params, self.queue_out
                )
                thread.set_confidence_thresholds(self.conf_thresholds)
                thread.start()
                self.detection_threads.append(thread)
            except Exception as e:
                return False
        return True

    def reset_impl(self):
        super().reset_impl()

    def set_params_impl(self):
        super().set_params_impl()
        self.model_name = self.params.get('model', self.model_name)
        self.attrs = self.params.get('attrs', self.attrs)
        self.conf_thresholds = self.params.get('confidence_thresholds', {})

    def get_params_impl(self):
        params = super().get_params_impl()
        params['model'] = self.model_name
        params['attrs'] = self.attrs
        params['confidence_thresholds'] = self.conf_thresholds
        return params

    def get_debug_info(self, debug_info: dict):
        super().get_debug_info(debug_info)
        debug_info['model_name'] = self.model_name
        debug_info['attrs'] = self.attrs

    def default(self):
        self.params.clear()
