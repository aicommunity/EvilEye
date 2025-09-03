import cv2
import numpy as np
from .background_subtraction_base import BackgroundSubtractorBase


class BackgroundSubtractorMOG2(BackgroundSubtractorBase):
    def __init__(self):
        super().__init__()
        self.subtractor = cv2.createBackgroundSubtractorMOG2()

    def set_params_impl(self):
        self.subtractor.setHistory(self.params['history'])
        self.subtractor.setVarThreshold(self.params['varThreshold'])
        self.subtractor.setDetectShadows(self.params['detectShadows'])

    def default(self):
        self.params['history'] = 500
        self.params['varThreshold'] = 16.0
        self.params['detectShadows'] = True
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
            roi = image[y0:y + min(2 * height, image.shape[0]), x0:x + min(2 * width, image.shape[1])]  # Получаем ROI из кадра
            roi = roi.astype(np.uint8)
            roi = cv2.cvtColor(roi, cv2.COLOR_GRAY2BGR)
            all_roi.append([roi, [x0, y0]])
        return foreground_mask, all_roi

    @staticmethod
    def apply_morphology(foreground_mask):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # Ядро для морфологических операций
        opening = cv2.morphologyEx(foreground_mask, cv2.MORPH_OPEN, kernel)  # Эрозия + Дилатация, чтобы избавиться от шума
        dilation = cv2.dilate(opening, np.ones((5, 5), np.uint8), iterations=7)  # Дилатация, чтобы сделать контуры больше
        return dilation
