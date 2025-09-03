import copy
import datetime
from abc import ABC, abstractmethod
import threading
from queue import Queue
from enum import Enum
from urllib.parse import urlparse
from threading import Lock
from collections import deque
from ..core.base_class import EvilEyeBase
from ..core.frame import CaptureImage, Frame


class CaptureDeviceType(Enum):
    VideoFile = "VideoFile"
    IpCamera = "IpCamera"
    Device = "Device"
    NotSet = "NotSet"

class VideoCaptureBase(EvilEyeBase):
    def __init__(self):
        super().__init__()
        self.source_address = None
        self.username = None
        self.password = None
        self.pure_url = None
        self.run_flag = False
        self.frames_queue = Queue(maxsize=2)
        self.frame_id_counter = 0
        self.source_type = CaptureDeviceType.NotSet
        self.source_fps = None
        self.desired_fps = None
        self.split_stream = False
        self.num_split = 0
        self.src_coords = None
        self.source_ids = None
        self.source_names = None
        self.finished = False
        self.loop_play = True
        self.video_duration = None
        self.video_length = None
        self.video_current_frame = None
        self.video_current_position = None
        self.is_working = False
        self.conn_mutex = Lock()
        self.disconnects = []
        self.reconnects = []
        self.subscribers = []

        self.capture_thread = None
        self.grab_thread = None
        self.retrieve_thread = None

    def is_opened(self) -> bool:
        return False

    def is_working(self) -> bool:
        return self.is_working

    def is_finished(self) -> bool:
        return self.finished

    def is_running(self):
        return self.run_flag

    def get(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            captured_images = self.get_frames_impl()
        return captured_images

    def start(self):
        if not self.is_inited:
            return
        self.run_flag = True
        # self.capture_thread = threading.Thread(target=self._capture_frames)
        # self.capture_thread.start()
        self.grab_thread = threading.Thread(target=self._grab_frames)
        self.retrieve_thread = threading.Thread(target=self._retrieve_frames)
        self.grab_thread.start()
        self.retrieve_thread.start()

    def stop(self):
        self.run_flag = False
        # if self.capture_thread:
        #     self.capture_thread.join()
        #     self.capture_thread = None
        #     print('Capture stopped')
        if self.grab_thread:
            if self.grab_thread.is_alive():
                self.grab_thread.join()
            self.grab_thread = None
        if self.retrieve_thread:
            if self.retrieve_thread.is_alive():
                self.retrieve_thread.join()
            self.retrieve_thread = None

    def set_params_impl(self):
        self.release()
        self.split_stream = self.params.get('split', False)
        self.num_split = self.params.get('num_split', None)
        self.src_coords = self.params.get('src_coords', None)
        self.source_ids = self.params.get('source_ids', None)
        self.desired_fps = self.params.get('desired_fps', None)
        self.source_names = self.params.get('source_names', self.source_ids)
        self.loop_play = self.params.get('loop_play', True)
        source_param = self.params.get('source', "")
        if source_param:
            self.source_type = CaptureDeviceType[source_param]
        else:
            self.source_type = CaptureDeviceType.NotSet
        self.source_address = self.params.get('camera', '')
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

    def get_params_impl(self):
        params = dict()
        params['split'] = self.split_stream
        params['num_split'] = self.num_split
        params['src_coords'] = self.src_coords
        params['source_ids'] = self.source_ids
        params['desired_fps'] = self.desired_fps
        params['source_names'] = self.source_names
        params['loop_play'] = self.loop_play
        params['source'] = self.source_type.name
        params['camera'] = self.source_address
        return params

    def get_disconnects_info(self) -> list[tuple[str, datetime.datetime, bool]]:
        disconnects = copy.deepcopy(self.disconnects)
        self.disconnects = []
        return disconnects

    def get_reconnects_info(self) -> list[tuple[str, datetime.datetime, bool]]:
        reconnects = copy.deepcopy(self.reconnects)
        self.reconnects = []
        return reconnects

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

    def subscribe(self, *subscribers):
        self.subscribers = list(subscribers)

    # @abstractmethod
    # def _capture_frames(self):
    #     pass

    @abstractmethod
    def get_frames_impl(self) -> list[CaptureImage]:
        pass

    @abstractmethod
    def _grab_frames(self):
        pass

    @abstractmethod
    def _retrieve_frames(self):
        pass
