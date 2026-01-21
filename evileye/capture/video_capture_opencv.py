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
                result = self.capture.open(pipeline, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
                if not self.capture.isOpened():
                    self.logger.warning(f"Failed to open video file with GStreamer for {self.source_names}. Pipeline: {pipeline}")
            else:
                # If pipeline is already specified, use it directly
                result = self.capture.open(self.source_address, VideoCaptureOpencv.VideoCaptureAPIs[api_pref])
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
        # For video files we use read() in _retrieve_frames (single-threaded read path).
        # Here we keep a lightweight watchdog to recover from occasional OpenCV stalls.
        if self.source_type == CaptureDeviceType.VideoFile:
            while self.run_flag and not self.stop_event.is_set():
                try:
                    if self.last_frame_time is not None:
                        dt = (datetime.datetime.now() - self.last_frame_time).total_seconds()
                        if dt > self.capture_config.frame_timeout_seconds:
                            self.logger.warning(
                                f"No frames for {dt:.1f}s from video file {self.source_names}; resetting capture"
                            )
                            try:
                                # Request reopen; do the actual reset inside _retrieve_frames thread
                                # to avoid races/crashes inside ffmpeg.
                                self._reopen_requested = True
                            except Exception:
                                pass
                            # After reset, give some time to start reading
                            time.sleep(0.2)
                            continue
                except Exception:
                    pass
                time.sleep(0.5)
            return

        while self.run_flag and not self.stop_event.is_set():
            begin_it = timer()
            # Health check: if no frames for too long, trigger reconnect/reset
            if (
                self.source_type == CaptureDeviceType.IpCamera
                and self.last_frame_time
                and (datetime.datetime.now() - self.last_frame_time).total_seconds() > self.capture_config.frame_timeout_seconds
            ):
                self.logger.warning(
                    f"No frames for {self.capture_config.frame_timeout_seconds}s from {self.source_names}, forcing reset"
                )
                self.is_working = False
                self.reset()
            if not self.is_inited or self.capture is None:
                time.sleep(CaptureConstants.RECONNECT_SLEEP_SHORT)
                if self.init():
                    timestamp = datetime.datetime.now()
                    self.logger.info(f"Reconnected to a sources: {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                    self.reconnects.append((self.params['camera'], timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                else:
                    continue

            if not self.is_opened():
                time.sleep(CaptureConstants.RECONNECT_SLEEP_SHORT)
                self.reset()

            # Minimize lock hold time - only lock during actual grab operation
            with self.mutex:
                is_grabbed = self.capture.grab()
            if not is_grabbed:
                # End-of-file / grab failure handling
                if self.source_type == CaptureDeviceType.VideoFile:
                    if self.loop_play:
                        # Для роликов с зацикливанием не считаем это дисконнектом,
                        # просто перематываем на начало без тяжёлого reset()
                        try:
                            self.logger.info(f"End of video for {self.source_names}, looping from start")
                            self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                            self.video_current_frame = 0
                            self.video_current_position = 0.0
                            continue
                        except Exception as e:
                            self.logger.warning(f"Failed to loop video file for {self.source_names}, falling back to reset: {e}")
                            # если не смогли перемотать, используем старую схему reset()
                    else:
                        self.finished = True
                        self.run_flag = False
                        self.stop_event.set()
                        break

                # Для живых источников (или fallback для роликов) — старая логика reconnection
                self.is_working = False
                timestamp = datetime.datetime.now()
                self.disconnects.append((self.params['camera'], timestamp, self.is_working))
                for sub in self.subscribers:
                    sub.update()
                # reset() попытается восстановить поток
                self.reset()
                # Verify reset was successful
                if not (self.is_inited and self.is_opened()):
                    self.logger.warning(
                        f"Reset may have failed for {self.source_names} "
                        f"(is_inited={self.is_inited}, is_opened={self.is_opened()})"
                    )
                    self.run_flag = False
                    self.stop_event.set()

            end_it = timer()
            elapsed_seconds = end_it - begin_it
            sleep_seconds = self._calculate_sleep_seconds(elapsed_seconds)
            time.sleep(sleep_seconds)

    def _retrieve_frames(self) -> None:
        consecutive_failures = 0
        # For VideoFile sources, OpenCV/FFmpeg may occasionally block inside read().
        # Use a single-worker executor + timeout to detect and recover from such stalls.
        executor = None
        if self.source_type == CaptureDeviceType.VideoFile:
            try:
                from concurrent.futures import ThreadPoolExecutor
                executor = ThreadPoolExecutor(max_workers=1)
            except Exception:
                executor = None

        while self.run_flag and not self.stop_event.is_set():
            begin_it = timer()
            try:
                if self.source_type == CaptureDeviceType.VideoFile:
                    if getattr(self, "_reopen_requested", False):
                        try:
                            self.logger.info(f"Reopening video capture for {self.source_names} (watchdog requested)")
                            self.reset_impl()
                        except Exception as e:
                            self.logger.warning(f"Failed to reopen capture for {self.source_names}: {e}")
                        finally:
                            self._reopen_requested = False
                    # For file sources, use read() to avoid grab/retrieve desynchronization.
                    # Intentionally do NOT hold mutex during read(): it may block in OpenCV.
                    if executor is not None:
                        try:
                            fut = executor.submit(self.capture.read)
                            is_read, src_image = fut.result(timeout=1.0)
                        except Exception as e:
                            # Timeout or worker exception — attempt to recover by reopening.
                            consecutive_failures += 1
                            self.logger.warning(f"Video read timeout/stall for {self.source_names}: {e}. Reopening capture.")
                            try:
                                self.reset_impl()
                            except Exception:
                                pass
                            time.sleep(0.1)
                            continue
                    else:
                        is_read, src_image = self.capture.read()
                    if not is_read or src_image is None:
                        consecutive_failures += 1
                        if self.loop_play:
                            # If we can't read for a while, perform a full reset (re-open file)
                            if consecutive_failures >= 30:
                                self.logger.warning(
                                    f"Video read stalled for {self.source_names} (failures={consecutive_failures}), resetting capture"
                                )
                                try:
                                    self.reset()
                                except Exception:
                                    pass
                                consecutive_failures = 0
                            else:
                                try:
                                    self.logger.info(f"End of video for {self.source_names}, looping from start")
                                    with self.mutex:
                                        self.capture.set(cv2.CAP_PROP_POS_FRAMES, 0)
                                    self.video_current_frame = 0
                                    self.video_current_position = 0.0
                                except Exception as e:
                                    self.logger.warning(f"Failed to loop video file for {self.source_names}: {e}")
                                    try:
                                        self.reset()
                                    except Exception:
                                        pass
                                    consecutive_failures = 0
                            # small sleep to avoid tight loop
                            time.sleep(self.capture_config.min_sleep_seconds)
                            continue
                        else:
                            self.finished = True
                            self.run_flag = False
                            self.stop_event.set()
                            break
                    else:
                        consecutive_failures = 0
                        self.last_frame_time = datetime.datetime.now()
                else:
                    # Minimize lock hold time - only lock during actual retrieve operation
                    with self.mutex:
                        is_read, src_image = self.capture.retrieve()
            except Exception as e:
                consecutive_failures += 1
                self.logger.error(f"Exception in _retrieve_frames for {self.source_names}: {e}", exc_info=True)
                # Try to recover for video files
                if self.source_type == CaptureDeviceType.VideoFile:
                    try:
                        self.reset()
                    except Exception:
                        pass
                time.sleep(self.capture_config.min_sleep_seconds)
                continue
            if is_read:
                self._process_frame_metadata(is_read)
                # DropOldestQueue automatically drops oldest when full
                dropped = False
                try:
                    dropped = self.frames_queue.put([is_read, src_image, self.frame_id_counter, self.video_current_frame, self.video_current_position])
                except TypeError:
                    # Standard Queue for VideoFile returns None; keep behavior
                    dropped = False
                if dropped:
                    self.dropped_frames += 1
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

            retrieve_fps = self.desired_fps if self.desired_fps else self.source_fps if self.source_fps else self.capture_config.default_fps_fallback
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
