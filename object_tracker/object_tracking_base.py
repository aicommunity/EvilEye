import numpy as np
from abc import ABC, abstractmethod
import core


class ObjectTrackingBase(core.EvilEyeBase):
    def process(
            self, 
            det_info: dict,
            is_actual: bool = True, 
            img: np.ndarray = None):
        
        if self.get_init_flag():
            return self.process_impl(det_info, is_actual, img)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, image, bboxes):
        pass
