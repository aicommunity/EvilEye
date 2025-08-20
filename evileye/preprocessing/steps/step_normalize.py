import cv2
from .step_abstract import StepAbstarct

class Normalize(StepAbstarct):
    def __init__(self, aNextStep=None, alpha=0, beta=255):
        super().__init__(aNextStep)
        self.alpha = alpha
        self.beta = beta
        
    def _applyStep(self, aFrame):
        return cv2.normalize(aFrame, None, alpha=self.alpha, beta=self.beta, norm_type=cv2.NORM_MINMAX)
        
          