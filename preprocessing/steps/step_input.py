import cv2
from .step_abstract import StepAbstarct

class PreprocessInput(StepAbstarct):
    def __init__(self, aNextStep=None):
        super().__init__(aNextStep)
        
    def _applyStep(self, aFrame):
        return aFrame

        
          