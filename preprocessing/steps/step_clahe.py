import cv2
from .step_abstract import StepAbstarct


'''
https://docs.opencv.org/4.x/d5/daf/tutorial_py_histogram_equalization.html
'''
class Clahe(StepAbstarct):
    def __init__(self, aNextStep=None, clipLimit=2.0, tileGridSize=(8,8)):
        super().__init__(aNextStep)
        self.claheFilter = cv2.createCLAHE(clipLimit, tileGridSize)
        
    def _applyStep(self, aFrame):
        labImg = cv2.cvtColor(aFrame, cv2.COLOR_BGR2LAB)
        labPlanes = list(cv2.split(labImg))  # Convert to list for mutable access
        labPlanes[0] = self.claheFilter.apply(labPlanes[0])
        labImg = cv2.merge(labPlanes)
        return cv2.cvtColor(labImg, cv2.COLOR_LAB2BGR)

        
          