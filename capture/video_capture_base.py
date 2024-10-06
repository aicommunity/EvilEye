from abc import ABC, abstractmethod
import cv2
import core
from enum import IntEnum
import threading
from queue import Queue


class CaptureImage:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.image = None


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

        self.run_flag = False
        self.frames_queue = Queue(maxsize=2)
        self.writer = threading.Thread(target=self._capture_frames)
        self.frame_id_counter = 0

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
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            captured_images = self.process_impl(split_stream, num_split, src_coords)
        else:
            print('init function has not been called')
        return captured_images

    def start(self):
        self.run_flag = True
        self.writer.start()

    def stop(self):
        self.run_flag = False
        self.writer.join()
        self.release()
        print('Capture stopped')

    @abstractmethod
    def _capture_frames(self):
        pass

    @abstractmethod
    def process_impl(self, split_stream=False, num_split=None, src_coords=None):
        pass
