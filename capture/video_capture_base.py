from abc import ABC, abstractmethod
import core
import threading
from queue import Queue
from enum import Enum
from urllib.parse import urlparse

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
        self.source_address = None
        self.username = None
        self.password = None
        self.pure_url = None
        self.run_flag = False
        self.frames_queue = Queue(maxsize=2)
        self.frame_id_counter = 0
        self.source_type = None
        self.source_fps = None
        self.desired_fps = None
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

        self.capture_thread = None

    def is_opened(self) -> bool:
        return False

    def is_finished(self) -> bool:
        return self.finished

    def is_running(self):
        return self.run_flag

    def get_frames(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            captured_images = self.get_frames_impl()
        return captured_images

    def start(self):
        if not self.is_inited:
            return
        self.run_flag = True
        self.capture_thread = threading.Thread(target=self._capture_frames)
        self.capture_thread.start()

    def stop(self):
        self.run_flag = False
        if self.capture_thread:
            self.capture_thread.join()
            self.capture_thread = None
            print('Capture stopped')

    def set_params_impl(self):
        self.release()
        self.split_stream = self.params.get('split', False)
        self.num_split = self.params.get('num_split', None)
        self.src_coords = self.params.get('src_coords', None)
        self.source_ids = self.params.get('source_ids', None)
        self.desired_fps = self.params.get('desired_fps', None)
        self.source_names = self.params.get('source_names', self.source_ids)
        self.loop_play = self.params.get('loop_play', True)
        self.source_type = CaptureDeviceType[self.params.get('source', "")]
        self.source_address = self.params['camera']
        if self.source_type == CaptureDeviceType.IpCamera:
            parsed = urlparse(self.source_address)
            self.username = parsed.username
            self.password = parsed.password
            replaced_url = parsed._replace(netloc=f"{parsed.hostname}")
            self.pure_url = replaced_url.geturl()
            self.username = self.params.get('username', self.username)
            self.password = self.params.get('password', self.password)
            self.source_address = self.reconstruct_url(replaced_url, self.username, self.password)
        else:
            self.username = None
            self.password = None
            self.pure_url = None

    @staticmethod
    def reconstruct_url(url_parsed_info, username, password):
        processed_username = username if (username and username != "") else None
        processed_password = password if (password and password != "") else None
        if not processed_password and not processed_username:
            return url_parsed_info.geturl()

        if not processed_password:
            reconstructed_url = url_parsed_info._replace(netloc=f"{processed_username}@{url_parsed_info.hostname}")
            return reconstructed_url.geturl()

        reconstructed_url = url_parsed_info._replace(netloc=f"{processed_username}:{processed_password}@{url_parsed_info.hostname}")
        return reconstructed_url.geturl()

    @abstractmethod
    def _capture_frames(self):
        pass

    @abstractmethod
    def get_frames_impl(self) -> list[CaptureImage]:
        pass
