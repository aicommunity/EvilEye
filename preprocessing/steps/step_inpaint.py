import cv2
from .step_abstract import StepAbstarct


'''
https://docs.opencv.org/3.4/df/d3d/tutorial_py_inpainting.html
'''
class Inpaint(StepAbstarct):
    def __init__(self, aNextStep=None):
        super().__init__(aNextStep)
        
    def _applyStep(self, aFrame):
        # Making mask
        grayImg = cv2.cvtColor(aFrame, cv2.COLOR_BGR2GRAY)
        mask = cv2.threshold(grayImg , 220, 255, cv2.THRESH_BINARY)[1]
        
        # Inpainting
        return cv2.inpaint(aFrame, mask, 0.1, cv2.INPAINT_TELEA) 

        
          