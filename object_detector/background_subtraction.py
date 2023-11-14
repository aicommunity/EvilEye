from abc import ABC, abstractmethod
import cv2
import numpy as np


class BackgroundSubtractor(ABC):

    @abstractmethod
    def get_roi(self, image, foreground_mask):
        pass


class BackgroundSubtractorMOG2(BackgroundSubtractor, cv2.BackgroundSubtractorMOG2):

    def __init__(self, history=500, var_threshold=16, detect_shadows=True):
        self.subtractor = cv2.createBackgroundSubtractorMOG2(history, var_threshold, detect_shadows)

    def get_roi(self, image, foreground_mask):
        all_roi = []
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
        return all_roi

    @staticmethod
    def apply_morphology(foreground_mask):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # Ядро для морфологических операций
        opening = cv2.morphologyEx(foreground_mask, cv2.MORPH_OPEN, kernel)  # Эрозия + Дилатация, чтобы избавиться от шума
        dilation = cv2.dilate(opening, np.ones((5, 5), np.uint8), iterations=5)  # Дилатация, чтобы сделать контуры больше
        return dilation
