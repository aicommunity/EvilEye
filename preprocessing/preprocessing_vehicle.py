import copy

import cv2
import numpy as np
from utils import utils
from preprocessing import PreprocessingBase
from preprocessing.steps import PreprocessInput


class PreprocessingVehicle(PreprocessingBase):
    def __init__(self):
        super().__init__()
        self.inputStep = PreprocessInput()

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
        processed_image = image
        # processed_image = copy.deepcopy(image)  # Todo: its trivial
        processed_image.image = self.inputStep.applySequence(image.image)
        return processed_image

