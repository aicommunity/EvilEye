import cv2
import numpy as np
from .background_subtraction_base import BackgroundSubtractorBase
from .constants import (
    DEFAULT_BG_DETECT_SHADOWS,
    DEFAULT_BG_HISTORY,
    DEFAULT_BG_VAR_THRESHOLD,
)


class BackgroundSubtractorMOG2(BackgroundSubtractorBase):
    def __init__(self):
        super().__init__()
        self.subtractor = cv2.createBackgroundSubtractorMOG2()

    def set_params_impl(self):
        self.subtractor.setHistory(self.params['history'])
        self.subtractor.setVarThreshold(self.params['varThreshold'])
        self.subtractor.setDetectShadows(self.params['detectShadows'])

    def default(self):
        self.params['history'] = DEFAULT_BG_HISTORY
        self.params['varThreshold'] = DEFAULT_BG_VAR_THRESHOLD
        self.params['detectShadows'] = DEFAULT_BG_DETECT_SHADOWS
        self.set_params_impl()

    def init_impl(self):
        return True

    def reset_impl(self):
        pass

    def process_impl(self, image):
        all_roi = []
        foreground_mask = self.subtractor.apply(image)
        dilation = self.apply_morphology(foreground_mask)
        contours, _ = cv2.findContours(dilation, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for contour in contours:
            x, y, width, height = cv2.boundingRect(contour)
            x0 = x - min(x, width)
            y0 = y - min(y, height)
            roi = image[y0:y + min(2 * height, image.shape[0]), x0:x + min(2 * width, image.shape[1])]  # Extract ROI from frame
            roi = roi.astype(np.uint8)
            roi = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
            all_roi.append([roi, [x0, y0]])
        return foreground_mask, all_roi

    @staticmethod
    def apply_morphology(foreground_mask):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # Kernel for morphological operations
        opening = cv2.morphologyEx(foreground_mask, cv2.MORPH_OPEN, kernel)  # Erosion + Dilation to remove noise
        dilation = cv2.dilate(opening, np.ones((5, 5), np.uint8), iterations=7)  # Dilation to make contours larger
        return dilation
