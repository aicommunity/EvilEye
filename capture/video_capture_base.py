from abc import ABC, abstractmethod
import numpy as np
import cv2
import core
from enum import IntEnum


class VideoCaptureBase(core.EvilEyeBase):
    source_count = 0
    video_sources = []

    class VideoCaptureAPIs(IntEnum):
        CAP_ANY = 0
        CAP_GSTREAMER = 1800
        CAP_FFMPEG = 1900
        CAP_IMAGES = 2000

    def __init__(self):
        super().__init__()
        self.capture = cv2.VideoCapture()
        self.stream_idx = VideoCaptureBase.source_count
        VideoCaptureBase.video_sources.append(self.capture)
        VideoCaptureBase.source_count += 1

    def is_opened(self):
        return self.capture.isOpened()

    def release(self):
        VideoCaptureBase.source_count -= 1
        del VideoCaptureBase.video_sources[self.stream_idx]
        self.capture.release()

    @classmethod
    def get_src_by_index(cls, index):
        return cls.video_sources[index]

    def process(self, split_stream=False, num_split=None, roi=None):
        if self.get_init_flag():
            return self.process_impl(split_stream, num_split, roi)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, split_stream=False, num_split=None, roi=None):
        pass
