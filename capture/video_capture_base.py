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
        self.capture.release()
        VideoCaptureBase.video_sources[self.stream_idx] = None

    @classmethod
    def get_src_by_index(cls, index):
        try:
            return cls.video_sources[index]
        except IndexError:
            print('Source index is out of range')

    def process(self, split_stream=False, num_split=None, src_coords=None):
        if self.get_init_flag():
            return self.process_impl(split_stream, num_split, src_coords)
        else:
            raise Exception('init function has not been called')

    @abstractmethod
    def process_impl(self, split_stream=False, num_split=None, src_coords=None):
        pass
