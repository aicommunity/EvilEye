from abc import ABC, abstractmethod
import core
import threading
from queue import Queue


class CaptureImage:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.time_stamp = None
        self.image = None


class VideoCaptureBase(core.EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.run_flag = False
        self.frames_queue = Queue(maxsize=1)
        self.frame_id_counter = 0
        self.source_fps = None
        self.split_stream = False
        self.num_split = None
        self.src_coords = None
        self.capture_thread = threading.Thread(target=self._capture_frames)

    def is_opened(self) -> bool:
        return False

    def get_frames(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            captured_images = self.get_frames_impl()
        else:
            raise Exception('init function has not been called')
        return captured_images

    def start(self):
        self.run_flag = True
        self.capture_thread.start()

    def stop(self):
        self.run_flag = False
        self.capture_thread.join()
        self.release()
        print('Capture stopped')

    @abstractmethod
    def _capture_frames(self):
        pass

    @abstractmethod
    def get_frames_impl(self) -> list[CaptureImage]:
        pass
