from abc import ABC, abstractmethod
import numpy as np
import cv2
import core


class VideoCaptureBase(core.EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.capture = cv2.VideoCapture()

    def is_opened(self):
        return self.capture.isOpened()

    def release(self):
        self.capture.release()

    def process(self):
        if self.get_init_flag():
            return self.process_impl()
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self):
        pass
