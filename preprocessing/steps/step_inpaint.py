import cv2
from .step_abstract import StepAbstarct


'''
https://docs.opencv.org/3.4/df/d3d/tutorial_py_inpainting.html
'''
class Inpaint(StepAbstarct):
    def __init__(self, aNextStep=None, thresholdMin=100, thresholdMax=255, inpaintRadius=0.1):
        super().__init__(aNextStep)
        self.thresholdMin = thresholdMin
        self.thresholdMax = thresholdMax
        self.inpaintRadius = inpaintRadius
        
    def _applyStep(self, aFrame):
        # Making mask
        grayImg = cv2.cvtColor(aFrame, cv2.COLOR_BGR2GRAY)
        mask = cv2.threshold(grayImg , self.thresholdMin, self.thresholdMax, cv2.THRESH_BINARY)[1]
        
        # Inpainting
        return cv2.inpaint(aFrame, mask, self.inpaintRadius, cv2.INPAINT_TELEA) 

        
          