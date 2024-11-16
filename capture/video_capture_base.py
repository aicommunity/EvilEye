from abc import ABC, abstractmethod
import core
import threading
from queue import Queue
from enum import Enum

class CaptureDeviceType(Enum):
    VideoFile = "VideoFile"
    IpCamera = "IpCamera"
    Device = "Device"


class CaptureImage:
    def __init__(self):
        self.source_id = None
        self.frame_id = None
        self.current_video_frame = None
        self.current_video_position = None
        self.time_stamp = None
        self.image = None


class VideoCaptureBase(core.EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.run_flag = False
        self.frames_queue = Queue(maxsize=2)
        self.frame_id_counter = 0
        self.source_type = None
        self.source_fps = None
        self.split_stream = False
        self.num_split = None
        self.src_coords = None
        self.source_ids = None
        self.source_names = None
        self.finished = False
        self.loop_play = True
        self.video_duration = None
        self.video_length = None
        self.video_current_frame = None
        self.video_current_position = None

        self.capture_thread = threading.Thread(target=self._capture_frames)

    def is_opened(self) -> bool:
        return False

    def is_finished(self) -> bool:
        return self.finished

    def get_frames(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            captured_images = self.get_frames_impl()
        else:
            raise Exception('init function has not been called')
        return captured_images

    def start(self):
        self.init()
        self.run_flag = True
        self.capture_thread.start()

    def stop(self):
        self.run_flag = False
        self.capture_thread.join()
        self.release()
        print('Capture stopped')

    def set_params_impl(self):
        self.release()
        self.split_stream = self.params.get('split', False)
        self.num_split = self.params.get('num_split', None)
        self.src_coords = self.params.get('src_coords', None)
        self.source_ids = self.params.get('source_ids', None)
        self.source_names = self.params.get('source_names', self.source_ids)
        self.loop_play = self.params.get('loop_play', True)
        self.source_type = CaptureDeviceType[self.params.get('source', "")]

    @abstractmethod
    def _capture_frames(self):
        pass

    @abstractmethod
    def get_frames_impl(self) -> list[CaptureImage]:
        pass
