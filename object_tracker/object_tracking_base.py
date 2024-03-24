import numpy as np
from abc import ABC, abstractmethod
import core


class ObjectTrackingBase(core.EvilEyeBase):
    def process(
            self, 
            bboxes_coords: np.ndarray, 
            confidences: np.ndarray, 
            class_ids: np.ndarray, 
            is_actual: bool = True, 
            img: np.ndarray = None):
        
        if self.get_init_flag():
            return self.process_impl(bboxes_coords, confidences, class_ids, is_actual, img)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, image, bboxes):
        pass
