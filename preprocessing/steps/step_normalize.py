import cv2
from .step_abstract import StepAbstarct

class Normalize(StepAbstarct):
    def __init__(self, aNextStep=None):
        super().__init__(aNextStep)
        
    def _applyStep(self, aFrame):
        return cv2.normalize(aFrame, None, alpha=0, beta=255, norm_type=cv2.NORM_MINMAX)
        
          