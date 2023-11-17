import background_subtraction_base as base
import cv2
import numpy as np


class BackgroundSubtractorMOG2(base.BackgroundSubtractor):
    def __init__(self):
        super().__init__()
        self.subtractor = cv2.createBackgroundSubtractorMOG2()

    def set_params(self, **params):
        self.subtractor.setHistory(params['history'])
        self.subtractor.setVarThreshold(params['varThreshold'])
        self.subtractor.setDetectShadows(params['detectShadows'])

    def get_params(self):
        params = {'history': self.subtractor.getHistory(), 'varThreshold': self.subtractor.getVarThreshold(),
                  'detectShadows': self.subtractor.getDetectShadows()}
        return params

    def default(self):
        self.subtractor.setHistory(500)
        self.subtractor.setVarThreshold(16.0)
        self.subtractor.setDetectShadows(True)

    def apply(self, image):
        return self.subtractor.apply(image)

    def get_roi(self, image, foreground_mask):
        all_roi = []
        dilation = self.apply_morphology(foreground_mask)
        # cv2.imshow("DIl2", dilation)
        # cv2.waitKey(0)
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

    def init(self):
        self.is_inited = True

    def areset(self):
        pass

    @staticmethod
    def apply_morphology(foreground_mask):
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))  # Ядро для морфологических операций
        opening = cv2.morphologyEx(foreground_mask, cv2.MORPH_OPEN, kernel)  # Эрозия + Дилатация, чтобы избавиться от шума
        dilation = cv2.dilate(opening, np.ones((5, 5), np.uint8), iterations=7)  # Дилатация, чтобы сделать контуры больше
        return dilation
