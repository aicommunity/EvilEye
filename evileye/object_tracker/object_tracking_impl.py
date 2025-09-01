import cv2
import numpy as np
from utils import utils
from object_tracker import object_tracking_base


class ObjectTrackingImpl(object_tracking_base.ObjectTrackingBase):
    def __init__(self):
        super().__init__()

    def init_impl(self):
        return True

    def reset_impl(self):
        pass

    def set_params_impl(self):
        pass

    def default(self):
        self.params.clear()

    def process_impl(self, image, bboxes):
        pass
