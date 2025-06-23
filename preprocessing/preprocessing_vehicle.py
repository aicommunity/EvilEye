import copy

import cv2
import numpy as np
from utils import utils
from preprocessing import PreprocessingBase, PreprocessingFactory
# from preprocessing.steps import Input, Normalize, Output, Inpaint, Clahe


class PreprocessingVehicle(PreprocessingBase):
    def __init__(self):
        super().__init__()
        json_path = 'samples/vehicle_perpocessing.json'
        factory = PreprocessingFactory(json_path)
        self.preprocessSequence = factory.build_pipeline()
    
        # self.preprocessSequence = Input(Normalize(Inpaint(Clahe(Output()))))
        

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
        processed_image.image = self.preprocessSequence.applySequence(image.image)
        
        return processed_image

