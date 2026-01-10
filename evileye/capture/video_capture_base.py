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
from ..video_recorder.recording_params import RecordingParams
from ..video_recorder.recorder_manager import RecorderManager
from ..core.frame import CaptureImage, Frame


class CaptureDeviceType(Enum):
    VideoFile = "VideoFile"
    IpCamera = "IpCamera"
    Device = "Device"
    ImageSequence = "ImageSequence"
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

        # Recording
        self.recording_params: RecordingParams | None = None
        self.recorder_manager: RecorderManager | None = None

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
        # Always start threads, even if not initialized - reconnect logic will handle it
        # This allows reconnect logic to work from the start
        self.run_flag = True
        # self.capture_thread = threading.Thread(target=self._capture_frames)
        # self.capture_thread.start()
        self.grab_thread = threading.Thread(target=self._grab_frames)
        self.retrieve_thread = threading.Thread(target=self._retrieve_frames)
        self.grab_thread.start()
        self.retrieve_thread.start()
        # Start recording if configured
        # For GStreamer backend, recording is integrated into capture pipeline via tee
        # For OpenCV backend, use separate recorder
        try:
            continuous_enabled = (self.recording_params and 
                                  (self.recording_params.continuous_recording_enabled or 
                                   (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
            self.logger.debug(f"Checking recording: params={self.recording_params is not None}, continuous_enabled={continuous_enabled}")
            if continuous_enabled:
                # Check if recording is integrated in pipeline (GStreamer) or separate (OpenCV)
                is_gstreamer = 'gstreamer' in self.__class__.__name__.lower()
                if is_gstreamer:
                    # GStreamer: recording is integrated in capture pipeline via tee
                    self.logger.info(f"Recording integrated in GStreamer capture pipeline for {self.source_names}")
                else:
                    # OpenCV: use separate recorder
                    backend = "opencv"
                    from ..video_recorder.recorder_base import SourceMeta
                    meta = SourceMeta(
                        source_name=(self.source_names[0] if self.source_names else "source"),
                        source_address=self.source_address,
                        source_type=str(self.source_type.value) if hasattr(self.source_type, 'value') else str(self.source_type),
                        width=None,
                        height=None,
                        fps=self.source_fps,
                        username=getattr(self, 'username', None),
                        password=getattr(self, 'password', None),
                        source_names=getattr(self, 'source_names', None),
                        source_ids=getattr(self, 'source_ids', None),
                    )
                    try:
                        # Sanitize credentials in URL for logs
                        url = str(meta.source_address)
                        try:
                            import re
                            # Mask rtsp://user:pass@host → rtsp://****:****@host
                            url = re.sub(r"rtsp:\/\/[^:@\/]+:[^@]+@", "rtsp://****:****@", url)
                            # Mask rtsp://user@host → rtsp://****@host
                            url = re.sub(r"rtsp:\/\/[^:@\/]+@", "rtsp://****@", url)
                        except Exception:
                            pass
                        self.logger.info(f"Starting recording: backend={backend} name={meta.source_name} url={url} out_dir={getattr(self.recording_params,'out_dir',None)}")
                    except Exception as e:
                        self.logger.error(f"Error logging recording start: {e}")
                    try:
                        self.recorder_manager = self.recorder_manager or RecorderManager()
                        self.recorder_manager.configure(self.recording_params)
                        self.recorder_manager.start(backend, meta)
                        self.logger.info(f"Recording started successfully for {meta.source_name}")
                    except Exception as e:
                        self.logger.error(f"Failed to start recording for {meta.source_name}: {e}", exc_info=True)
            else:
                continuous_enabled = (self.recording_params and 
                                      (self.recording_params.continuous_recording_enabled or 
                                       (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
                self.logger.debug(f"Recording not enabled or params missing: params={self.recording_params is not None}, continuous_enabled={continuous_enabled}")
        except Exception as e:
            self.logger.error(f"Error starting recording: {e}", exc_info=True)

    def stop(self):
        self.run_flag = False
        # Stop recording if running
        try:
            if self.recorder_manager:
                self.recorder_manager.stop()
        except Exception:
            pass
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
        # Recording params
        try:
            rec_cfg = self.params.get('record', None)
            if isinstance(rec_cfg, dict):
                self.recording_params = RecordingParams.from_config({'record': rec_cfg})
        except Exception:
            self.recording_params = None

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
        # CRITICAL: Save 'type' field to preserve VideoCaptureGStreamer vs VideoCaptureOpencv
        # Use class name from registry if available, otherwise use __class__.__name__
        # Prefer saved type from params if it was explicitly set
        if hasattr(self, 'params') and self.params and 'type' in self.params:
            params['type'] = self.params['type']
        else:
            # Use class name - this is the registered name in EvilEyeBase._registry
            params['type'] = self.__class__.__name__
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
