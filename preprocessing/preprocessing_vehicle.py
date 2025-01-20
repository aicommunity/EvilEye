import copy

import cv2
import numpy as np
from utils import utils
from preprocessing import PreprocessingBase


class PreprocessingVehicle(PreprocessingBase):
    def __init__(self):
        super().__init__()

    def init_impl(self):
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        super().set_params_impl()

    def default(self):
        self.params.clear()

    def _process_image(self, image):
        processed_image = None

        processed_image = copy.deepcopy(image)  # Todo: its trivial

        return processed_image

