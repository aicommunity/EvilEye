import datetime

import cv2
from threading import Lock, RLock
import time
from timeit import default_timer as timer
from .video_capture_base import VideoCaptureBase, CaptureImage, CaptureDeviceType
from .constants import CaptureConstants
from .exceptions import CaptureInitializationError, CaptureConnectionError
from enum import IntEnum

from ..core.base_class import EvilEyeBase
from ..video_recorder.recording_params import RecordingParams


@EvilEyeBase.register("VideoCaptureOpencv")
class VideoCaptureOpencv(VideoCaptureBase):
    class VideoCaptureAPIs(IntEnum):
        CAP_ANY = 0
        CAP_GSTREAMER = 1800
        CAP_FFMPEG = 1900
        CAP_IMAGES = 2000
    
    # Class variable to track already logged GStreamer errors
    _gstreamer_error_logged = set()  # Set of source_names for which error has already been logged

    def __init__(self):
        super().__init__()

        self.capture = cv2.VideoCapture()
        self.mutex = Lock()

    def is_opened(self) -> bool:
        return self.capture.isOpened()

    def set_params_impl(self) -> None:
        super().set_params_impl()
        try:
            rec_cfg = self.params.get('record', None)
            if isinstance(rec_cfg, dict):
                self.recording_params = RecordingParams.from_config({'record': rec_cfg})
        except Exception:
            pass

    def init_impl(self):
        api_pref = self.params.get('apiPreference','CAP_FFMPEG')
        
        # Check if GStreamer is requested but OpenCV doesn't support it
        if api_pref == "CAP_GSTREAMER":
            build_info = cv2.getBuildInformation()
            if "GStreamer:                   NO" in build_info or "GStreamer:                      NO" in build_info:
                # Log error only once per source set
                source_names_key = tuple(sorted(self.source_names)) if isinstance(self.source_names, list) else str(self.source_names)
                if source_names_key not in VideoCaptureOpencv._gstreamer_error_logged:
                    error_msg = (
                        f"apiPreference='CAP_GSTREAMER' is specified for {self.source_names}, "
                        f"but OpenCV was compiled WITHOUT GStreamer support. "
                        f"Please either:\n"
                        f"  1. Use 'type': 'VideoCaptureGStreamer' in source configuration instead of VideoCaptureOpencv, OR\n"
                        f"  2. Change apiPreference to 'CAP_FFMPEG' for VideoCaptureOpencv"
                    )
                    self.logger.error(f"ERROR: {error_msg}")
                    VideoCaptureOpencv._gstreamer_error_logged.add(source_names_key)
                    raise CaptureConfigurationError(error_msg)
                else:
                    # Log only at debug level for repeated attempts
                    self.logger.debug(
                        f"GStreamer not supported for {self.source_names} (error already logged, using reconnect logic)"
                    )
                return False
        
        if self.source_type == CaptureDeviceType.IpCamera and api_pref == "CAP_GSTREAMER":  # Convert RTSP URL to GStreamer format
            if '!' not in self.source_address:
                str_h265 = (' ! rtph265depay ! h265parse ! avdec_h265 ! decodebin ! videoconvert ! '  # Codec and format specification
                            'video/x-raw, format=(string)BGR ! appsink')
                str_h264 = (' ! rtph264depay ! h264parse ! avdec_h264 ! decodebin ! videoconvert ! '
                            'video/x-raw, format=(string)BGR ! appsink')

                if self.source_address.find('tcp') == 0:  # Set protocol
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='
                elif self.source_address.find('udp') == 0:
                    str1 = 'rtspsrc protocols=' + 'udp ' + 'location='
                else:
                    str1 = 'rtspsrc protocols=' + 'tcp ' + 'location='

                pos = self.source_address.find('rtsp')
                source = str1 + self.source_address[pos:] + str_h265
                self.capture.open(source, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
                if not self.is_opened():  # If H265 doesn't work, use H264
                    source = str1 + self.source_address + str_h264
                    self.capture.open(source, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
            else:
                self.capture.open(self.source_address, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
        elif self.source_type == CaptureDeviceType.VideoFile and api_pref == "CAP_GSTREAMER":
            # For video files with GStreamer, a special pipeline is needed
            if '!' not in self.source_address:
                # Build GStreamer pipeline for video file
                # Use decodebin for automatic codec detection
                pipeline = f'filesrc location={self.source_address} ! decodebin ! videoconvert ! video/x-raw,format=BGR ! appsink'
                self.logger.debug(f"Attempting to open video file with GStreamer pipeline: {pipeline[:100]}...")
                result = self.capture.open(pipeline, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
                self.logger.debug(f"GStreamer open() returned: {result}, isOpened(): {self.capture.isOpened()}")
                if not self.capture.isOpened():
                    self.logger.warning(f"Failed to open video file with GStreamer for {self.source_names}. Pipeline: {pipeline}")
            else:
                # If pipeline is already specified, use it directly
                self.logger.debug(f"Using provided GStreamer pipeline: {self.source_address[:100]}...")
                result = self.capture.open(self.source_address, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
                self.logger.debug(f"GStreamer open() returned: {result}, isOpened(): {self.capture.isOpened()}")
                if not self.capture.isOpened():
                    self.logger.warning(f"Failed to open video file with provided GStreamer pipeline for {self.source_names}")
        else:
            # For FFMPEG and other APIs, use direct file path
            self.capture.open(self.source_address, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])

        self.source_fps = None
        if self.capture.isOpened():
            self.is_working = True
            if self.source_type == CaptureDeviceType.VideoFile:
                self.video_length = self.capture.get(cv2.CAP_PROP_FRAME_COUNT)
                self.video_current_frame = 0
                self.video_current_position = 0.0
            self.finished = False
            try:
                self.source_fps = self.capture.get(cv2.CAP_PROP_FPS)
                if self.source_fps == 0.0:
                    self.source_fps = None
                    self.video_duration = None
                self.logger.info(f'FPS: {self.source_fps}')

                if self.source_fps is not None and self.source_type == CaptureDeviceType.VideoFile:
                    self.video_duration = self.video_length * 1000.0 / self.source_fps
            except cv2.error as e:
                self.logger.info(f"Failed to read source_fps: {e} for sources {self.source_names}")
        else:
            error_msg = f"Could not connect to sources: {self.source_names}"
            self.logger.error(error_msg)
            self.video_duration = None
            self.video_length = None
            self.video_current_frame = None
            self.video_current_position = None
            raise CaptureConnectionError(error_msg)

        return True

    def release_impl(self) -> None:
        self.capture.release()

    def reset_impl(self) -> None:
        self.logger.debug(f"reset_impl called for {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
        self.release()
        init_result = self.init()
        timestamp = datetime.datetime.now()
        if init_result and self.get_init_flag() and self.is_opened():
            self.logger.info(f"Reconnected to a sources: {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
            self.is_working = True
            self.reconnects.append((self.params['camera'], timestamp, self.is_working))
        else:
            self.logger.warning(f"Could not reconnect to sources: {self.source_names} (init_result={init_result}, is_inited={self.is_inited}, is_opened={self.is_opened()})")
            self.is_working = False
        for sub in self.subscribers:
            sub.update()

    def _grab_frames(self):
        while self.run_flag:
            begin_it = timer()
            if not self.is_inited or self.capture is None:
                self.logger.debug(f"Source {self.source_names} not initialized (is_inited={self.is_inited}, capture={self.capture is not None}), attempting reconnect")
                time.sleep(CaptureConstants.RECONNECT_SLEEP_SHORT)
                if self.init():
                    timestamp = datetime.datetime.now()
                    self.logger.info(f"Reconnected to a sources: {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                    self.reconnects.append((self.params['camera'], timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                else:
                    self.logger.debug(f"Reconnection attempt failed for {self.source_names} (init() returned False)")
                    continue

            if not self.is_opened():
                time.sleep(CaptureConstants.RECONNECT_SLEEP_SHORT)
                self.reset()

            # Minimize lock hold time - only lock during actual grab operation
            with self.mutex:
                is_grabbed = self.capture.grab()
            if not is_grabbed:
                if self.source_type != CaptureDeviceType.VideoFile or self.loop_play:
                    self.logger.debug(f"grab() failed for {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working}, loop_play={self.loop_play})")
                    self.is_working = False
                    timestamp = datetime.datetime.now()
                    self.disconnects.append((self.params['camera'], timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                    # For video files with loop_play, reset will restart from beginning
                    self.reset()
                    # Verify reset was successful
                    if self.is_inited and self.is_opened():
                        self.logger.debug(f"Reset successful for {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                    else:
                        self.logger.warning(f"Reset may have failed for {self.source_names} (is_inited={self.is_inited}, is_opened={self.is_opened()})")
                else:
                    self.finished = True

            end_it = timer()
            elapsed_seconds = end_it - begin_it
            sleep_seconds = self._calculate_sleep_seconds(elapsed_seconds)
            time.sleep(sleep_seconds)

    def _retrieve_frames(self) -> None:
        while self.run_flag:
            begin_it = timer()
            # Minimize lock hold time - only lock during actual retrieve operation
            with self.mutex:
                is_read, src_image = self.capture.retrieve()
            if is_read:
                self._process_frame_metadata(is_read)
                # DropOldestQueue automatically drops oldest when full
                self.frames_queue.put([is_read, src_image, self.frame_id_counter, self.video_current_frame, self.video_current_position])
                self.frame_id_counter += 1
                # Feed OpenCV recorder if present
                try:
                    if self.recorder_manager and getattr(self.recorder_manager, 'recorder', None):
                        rec = self.recorder_manager.recorder
                        on_frame = getattr(rec, 'on_frame', None)
                        if callable(on_frame):
                            on_frame(src_image)
                except Exception:
                    pass

            end_it = timer()
            elapsed_seconds = end_it - begin_it

            retrieve_fps = self.desired_fps if self.desired_fps else self.source_fps if self.source_fps else CaptureConstants.DEFAULT_FPS_FALLBACK
            sleep_seconds = self._calculate_sleep_seconds(elapsed_seconds, retrieve_fps)
            time.sleep(sleep_seconds)

        if not self.run_flag:
            self.logger.info('Not run flag')
            self._cleanup_queue()

    def get_frames_impl(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.frames_queue.empty():
            return captured_images
        ret, src_image, frame_id, current_video_frame, current_video_position = self.frames_queue.get()
        if ret:
            timestamp = time.time()
            if self.split_stream:
                captured_images = self._handle_split_stream(
                    src_image=src_image,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    current_video_frame=current_video_frame,
                    current_video_position=current_video_position
                )
            else:
                # No copy needed: src_image is already in queue and will be consumed immediately
                # Image reference is safe as it's removed from queue after this call
                source_id = self.source_ids[0] if self.source_ids else 0
                capture_image = self._create_capture_image(
                    image=src_image,
                    frame_id=frame_id,
                    timestamp=timestamp,
                    source_id=source_id,
                    current_video_frame=current_video_frame,
                    current_video_position=current_video_position
                )
                captured_images.append(capture_image)
        return captured_images

    def default(self):
        pass

    def get_params_impl(self):
        """Return capture parameters including OpenCV-specific fields.

        Adds 'apiPreference' to the base parameters to ensure it is persisted in configs.
        """
        params = super().get_params_impl()
        try:
            # Prefer the explicitly set parameter; default aligns with init_impl default
            params['apiPreference'] = self.params.get('apiPreference', 'CAP_FFMPEG')
            params['loop_play'] = self.loop_play
            params['split'] = self.split_stream
            params['num_split'] = self.num_split
            params['src_coords'] = self.src_coords
        except Exception:
            params['apiPreference'] = 'CAP_FFMPEG'
        return params

    def test_disconnect(self) -> None:
        with self.conn_mutex:
            timestamp = datetime.datetime.now()
            self.logger.info(f'Disconnect: {timestamp}')
            is_working = False
            self.disconnects.append((self.source_address, timestamp, is_working))

    def test_reconnect(self) -> None:
        with self.conn_mutex:
            timestamp = datetime.datetime.now()
            self.logger.info(f'Reconnect: {timestamp}')
            is_working = True
            self.reconnects.append((self.source_address, timestamp, is_working))
