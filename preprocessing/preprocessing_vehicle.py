import copy

import cv2
import numpy as np
from utils import utils
from preprocessing import PreprocessingBase, PreprocessingFactory
from core import EvilEyeBase
# from preprocessing.steps import Input, Normalize, Output, Inpaint, Clahe


@EvilEyeBase.register("PreprocessingVehicle")
class PreprocessingVehicle(PreprocessingBase):
    def __init__(self):
        super().__init__()
        self.json_path = None
        self.preprocessSequence = None

    def init_impl(self):
        self.json_path = 'samples/vehicle_perpocessing.json'
        factory = PreprocessingFactory(self.json_path)
        self.preprocessSequence = factory.build_pipeline()
        return True

    def release_impl(self):
        pass

    def reset_impl(self):
        pass

    def set_params_impl(self):
        super().set_params_impl()
        self.json_path = self.params['pipeline_file_name']

    def get_params_impl(self):
        params = super().get_params_impl()
        params['pipeline_file_name'] = self.json_path
        return params

    def default(self):
        self.params.clear()

    def _process_image(self, image):
        processed_image = image
        
        # processed_image = copy.deepcopy(image)  # Todo: its trivial
        processed_image.image = self.preprocessSequence.applySequence(image.image)
        
        return processed_image

