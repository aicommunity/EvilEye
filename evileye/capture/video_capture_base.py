import copy
import datetime
from abc import ABC, abstractmethod
import threading
from queue import Queue, Empty
from enum import Enum
from urllib.parse import urlparse, ParseResult
from threading import Lock, RLock
from collections import deque
from typing import Optional, Any
try:
    import numpy as np
except ImportError:
    np = None  # Type: ignore
from ..core.base_class import EvilEyeBase
from ..video_recorder.recording_params import RecordingParams
from ..video_recorder.recorder_manager import RecorderManager
from ..core.frame import CaptureImage, Frame
from .constants import CaptureConstants, CaptureConfig
from .queue_utils import DropOldestQueue

EXEC_MODE_THREAD = "thread"
EXEC_MODE_PROCESS = "process"


class CaptureDeviceType(Enum):
    VideoFile = "VideoFile"
    IpCamera = "IpCamera"
    Device = "Device"
    ImageSequence = "ImageSequence"
    NotSet = "NotSet"

class VideoCaptureBase(EvilEyeBase):
    def __init__(self):
        super().__init__()
        # Raw parameters passed from configuration / controller
        # Initialized here to avoid hasattr checks in methods
        self.params: dict | None = None
        self.source_address = None
        self.username = None
        self.password = None
        self.pure_url = None
        self.run_flag = False
        # Use optimized drop-oldest queue with deque for better performance
        # Size remains intentionally small to avoid stale frames
        self.capture_config = CaptureConfig()
        self.frames_queue = DropOldestQueue(maxsize=self.capture_config.queue_size)
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
        self.stop_event = threading.Event()
        self.dropped_frames = 0
        self.last_frame_time: datetime.datetime | None = None
        # Use RLock for connection mutex to allow nested locking if needed
        self.conn_mutex = RLock()
        self.disconnects = []
        self.reconnects = []
        self.subscribers = []

        # Recording
        self.recording_params: RecordingParams | None = None
        self.recorder_manager: RecorderManager | None = None

        self.capture_thread = None
        self.grab_thread = None
        self.retrieve_thread = None

        # Multiprocessing support (execution_mode == "process")
        self.execution_mode = EXEC_MODE_THREAD
        self._mp_control = None
        self._capture_dispatch_thread: threading.Thread | None = None

    def is_opened(self) -> bool:
        return False

    def is_working(self) -> bool:
        return self.is_working

    def is_finished(self) -> bool:
        return self.finished

    def is_running(self) -> bool:
        return self.run_flag

    def init(self, **kwargs):
        """Override to handle process-mode capture before subclass init."""
        if self.execution_mode == EXEC_MODE_PROCESS and not self.get_init_flag():
            self.is_inited = self._init_process_mode()
            return self.is_inited
        return super().init(**kwargs)

    def get(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            if self.execution_mode == EXEC_MODE_PROCESS:
                captured_images = self._get_frames_from_queue()
            else:
                captured_images = self.get_frames_impl()
        return captured_images

    def _get_frames_from_queue(self) -> list[CaptureImage]:
        """Read available frames from frames_queue (used in process mode)."""
        frames: list[CaptureImage] = []
        try:
            frame = self.frames_queue.get_nowait()
            if frame is not None:
                frames.append(frame)
        except Empty:
            pass
        return frames

    def _start_capture_threads(self) -> None:
        """Start capture threads (grab and retrieve).
        
        Always starts threads, even if not initialized - reconnect logic will handle it.
        This allows reconnect logic to work from the start.
        """
        self.stop_event.clear()
        self.run_flag = True
        self.grab_thread = threading.Thread(target=self._grab_frames, daemon=True)
        self.retrieve_thread = threading.Thread(target=self._retrieve_frames, daemon=True)
        self.grab_thread.start()
        self.retrieve_thread.start()

    def _start_recording(self) -> None:
        """Start recording if configured.
        
        For GStreamer backend, recording is integrated into capture pipeline via tee.
        For OpenCV backend, uses separate recorder.
        """
        if not self.recording_params:
            return
            
        try:
            # `enabled` is a master switch. Continuous recording must be explicitly enabled.
            continuous_enabled = bool(
                self.recording_params.enabled and self.recording_params.continuous_recording_enabled
            )
            
            if not continuous_enabled:
                return
            
            # Check if recording is integrated in pipeline (GStreamer) or separate (OpenCV)
            is_gstreamer = 'gstreamer' in self.__class__.__name__.lower()
            if is_gstreamer:
                # GStreamer: recording is integrated in capture pipeline via tee
                self.logger.info(f"Recording integrated in GStreamer capture pipeline for {self.source_names}")
            else:
                # OpenCV: use separate recorder
                self._start_opencv_recording()
        except Exception as e:
            self.logger.error(f"Error starting recording: {e}", exc_info=True)

    def _start_opencv_recording(self) -> None:
        """Start OpenCV recording with separate recorder."""
        backend = "opencv"
        from ..video_recorder.recorder_base import SourceMeta
        from ..video_recorder.continuous_recorder_manager import ContinuousRecorderManager
        
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
            url = self._sanitize_url_for_logging(str(meta.source_address))
            self.logger.info(f"Starting recording: backend={backend} name={meta.source_name} url={url} out_dir={getattr(self.recording_params,'out_dir',None)}")
        except Exception as e:
            self.logger.error(f"Error logging recording start: {e}")
        
        try:
            # Prefer continuous recorder manager if capture already set it up.
            if self.recorder_manager is None:
                self.recorder_manager = ContinuousRecorderManager(self.recording_params)
            self.recorder_manager.configure(self.recording_params)
            self.recorder_manager.start(backend, meta)
            self.logger.info(f"Recording started successfully for {meta.source_name}")
        except Exception as e:
            self.logger.error(f"Failed to start recording for {meta.source_name}: {e}", exc_info=True)

    def _sanitize_url_for_logging(self, url: str) -> str:
        """Sanitize URL by masking credentials for safe logging.
        
        Args:
            url: URL string that may contain credentials
            
        Returns:
            URL with credentials masked
        """
        try:
            import re
            # Mask rtsp://user:pass@host → rtsp://****:****@host
            url = re.sub(r"rtsp:\/\/[^:@\/]+:[^@]+@", "rtsp://****:****@", url)
            # Mask rtsp://user@host → rtsp://****@host
            url = re.sub(r"rtsp:\/\/[^:@\/]+@", "rtsp://****@", url)
        except Exception:
            pass
        return url

    def _notify_subscribers(self) -> None:
        """Notify all subscribers about state changes.
        
        This method can be overridden by subclasses for custom notification logic.
        """
        for sub in self.subscribers:
            try:
                if hasattr(sub, 'update'):
                    sub.update()
            except Exception:
                pass

    def _init_process_mode(self) -> bool:
        """Initialise MpControl + MpWorkerCapture for process-based capture."""
        from ..core.mp_control import MpControl
        from .mp_worker_capture import MpWorkerCapture

        self._mp_control = MpControl(
            max_input_size=4,
            name=f"capture-{'_'.join(str(s) for s in (self.source_ids or [0]))}",
        )
        worker = self._mp_control.add_worker(MpWorkerCapture)
        worker.set_params(self.params if self.params else {})
        self._mp_control.start()
        self.logger.info("Capture initialised in PROCESS mode")
        return True

    def _capture_dispatch_loop(self) -> None:
        """Read CaptureImage objects from child process and put them into frames_queue."""
        while self.run_flag:
            try:
                frame = self._mp_control.get(timeout=0.5)
            except Exception:
                continue
            if frame is None:
                continue
            try:
                self.frames_queue.put(frame)
            except Exception:
                pass

    def start(self) -> None:
        """Start video capture threads and recording."""
        if self.execution_mode == EXEC_MODE_PROCESS and self._mp_control is not None:
            self.run_flag = True
            self._capture_dispatch_thread = threading.Thread(
                target=self._capture_dispatch_loop, daemon=True,
            )
            self._capture_dispatch_thread.start()
            return
        self._start_capture_threads()
        self._start_recording()

    def stop(self) -> None:
        """Stop capture threads and recording, cleanup queues."""
        self.run_flag = False
        self.stop_event.set()

        if self._mp_control is not None:
            try:
                self._mp_control.stop()
            except Exception:
                pass
            self._mp_control = None
            if self._capture_dispatch_thread is not None:
                try:
                    self._capture_dispatch_thread.join(timeout=3.0)
                except Exception:
                    pass
                self._capture_dispatch_thread = None
            self._cleanup_queue()
            try:
                self.logger.info(f"Capture (process mode) stopped for {self.source_names}")
            except Exception:
                pass
            return

        try:
            if self.recorder_manager:
                self.recorder_manager.stop()
        except Exception:
            pass
        for thread_attr in ("grab_thread", "retrieve_thread"):
            t = getattr(self, thread_attr, None)
            if t:
                try:
                    t.join(timeout=2.0)
                except Exception:
                    pass
            setattr(self, thread_attr, None)
        self._cleanup_queue()
        try:
            self.logger.info(f"Capture stopped for {self.source_names}, dropped_frames={self.dropped_frames}")
        except Exception:
            pass

    def set_params_impl(self) -> None:
        self.release()
        self.execution_mode = self.params.get('execution_mode', EXEC_MODE_THREAD)
        self.capture_config = CaptureConfig.from_dict(self.params.get('capture'))
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

        # For video files use standard Queue to keep strict frame order (avoid aggressive dropping)
        # DropOldestQueue remains for live sources to prefer fresh frames.
        # NOTE: frames_queue is always DropOldestQueue.
        # Раньше для VideoFile использовался стандартный Queue,
        # теперь тип очереди унифицирован, чтобы не было разнородных реализаций.

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
        params['execution_mode'] = self.execution_mode
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
        if self.params and 'type' in self.params:
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
    def reconstruct_url(url_parsed_info: ParseResult, username: str | None, password: str | None) -> str:
        processed_username = username if (username and username != "") else None
        processed_password = password if (password and password != "") else None
        if not processed_password and not processed_username:
            return url_parsed_info.geturl()

        if not processed_password:
            reconstructed_url = url_parsed_info._replace(netloc=f"{processed_username}@{url_parsed_info.hostname}")
            return reconstructed_url.geturl()

        reconstructed_url = url_parsed_info._replace(netloc=f"{processed_username}:{processed_password}@{url_parsed_info.hostname}")
        return reconstructed_url.geturl()

    def get_ip_camera_init_hint(self) -> str:
        """Return a human-readable hint for common RTSP configuration mistakes."""
        if self.source_type != CaptureDeviceType.IpCamera:
            return ""

        hints: list[str] = []
        try:
            parsed = urlparse(self.source_address or "")
        except Exception:
            parsed = None

        has_username = bool(getattr(self, "username", None))
        has_password = bool(getattr(self, "password", None))
        has_credentials = has_username and has_password

        if not has_credentials:
            hints.append(
                "RTSP source is configured without username/password. "
                "If the camera requires authentication, add `username` and `password` to the source config "
                "or create `credentials.json` with credentials for this camera."
            )

        try:
            path = (parsed.path or "") if parsed is not None else ""
            if path in {"", "/"}:
                hints.append(
                    "RTSP URL looks incomplete (missing stream path). "
                    "Use a full stream URL like `rtsp://user:pass@host:554/stream_path`."
                )
        except Exception:
            pass

        return " ".join(hints)

    def subscribe(self, *subscribers):
        self.subscribers = list(subscribers)

    def _process_frame_metadata(self, frame_read: bool) -> None:
        """Update frame counters and positions after frame retrieval.
        
        Args:
            frame_read: Whether the frame was successfully read
        """
        if not frame_read:
            return

        if self.source_type == CaptureDeviceType.VideoFile:
            if self.video_current_frame is None:
                self.video_current_frame = 0
            else:
                self.video_current_frame += 1
            if self.source_fps and self.source_fps > 0.0:
                self.video_current_position = (self.video_current_frame * 1000.0) / self.source_fps
        elif self.source_type == CaptureDeviceType.IpCamera:
            self.last_frame_time = datetime.datetime.now()

    def _create_capture_image(
        self,
        image: np.ndarray,
        frame_id: int,
        timestamp: float,
        source_id: int,
        current_video_frame: int | None = None,
        current_video_position: float | None = None
    ) -> CaptureImage:
        """Create a CaptureImage object with metadata.
        
        Args:
            image: Image data (numpy array)
            frame_id: Frame ID counter value
            timestamp: Timestamp in seconds
            source_id: Source ID for this frame
            current_video_frame: Current video frame number (for video files)
            current_video_position: Current video position in milliseconds (for video files)
            
        Returns:
            CaptureImage instance with all metadata set
        """
        capture_image = CaptureImage()
        capture_image.image = image
        capture_image.frame_id = frame_id
        capture_image.time_stamp = timestamp
        capture_image.source_id = source_id
        capture_image.current_video_frame = current_video_frame if current_video_frame is not None else self.video_current_frame
        capture_image.current_video_position = current_video_position if current_video_position is not None else self.video_current_position
        capture_image.source_video_duration = self.video_duration
        return capture_image

    def _handle_split_stream(
        self,
        src_image: any,
        frame_id: int,
        timestamp: float,
        current_video_frame: int | None = None,
        current_video_position: float | None = None
    ) -> list[CaptureImage]:
        """Handle split stream processing - create multiple CaptureImage objects from single frame.
        
        Args:
            src_image: Source image to split
            frame_id: Frame ID counter value
            timestamp: Timestamp in seconds
            current_video_frame: Current video frame number (for video files)
            current_video_position: Current video position in milliseconds (for video files)
            
        Returns:
            List of CaptureImage objects, one for each split region
        """
        captured_images: list[CaptureImage] = []
        
        if not self.split_stream or not self.src_coords or not self.num_split:
            return captured_images
        
        for stream_cnt in range(self.num_split):
            if stream_cnt >= len(self.src_coords):
                continue
                
            # Extract region coordinates
            x, y, w, h = self.src_coords[stream_cnt]
            x, y, w, h = int(x), int(y), int(w), int(h)
            
            # Copy is necessary: extracted region must be independent from source image
            # Source image may be reused/modified, and split regions need to persist independently
            region = src_image[y:y+h, x:x+w].copy()
            
            # Get source ID for this split
            source_id = self.source_ids[stream_cnt] if self.source_ids and stream_cnt < len(self.source_ids) else stream_cnt
            
            # Create CaptureImage for this split region
            capture_image = self._create_capture_image(
                image=region,
                frame_id=frame_id,
                timestamp=timestamp,
                source_id=source_id,
                current_video_frame=current_video_frame,
                current_video_position=current_video_position
            )
            captured_images.append(capture_image)
        
        return captured_images

    def _cleanup_queue(self) -> None:
        """Clear all frames from the queue.
        
        This method is called when stopping capture to ensure no stale frames remain.
        """
        if not self.run_flag:
            # frames_queue всегда DropOldestQueue, у неё есть clear()
            self.frames_queue.clear()

    def _calculate_sleep_seconds(
        self,
        elapsed_seconds: float,
        fps: float | None = None,
        source_type: CaptureDeviceType | None = None
    ) -> float:
        """Calculate sleep interval based on FPS and elapsed time.
        
        Args:
            elapsed_seconds: Time elapsed during frame processing
            fps: Frames per second (uses source_fps if None)
            source_type: Source type (uses self.source_type if None)
            
        Returns:
            Sleep interval in seconds
        """
        if fps is None:
            fps = self.source_fps
        if source_type is None:
            source_type = self.source_type
            
        if fps and fps > 0:
            fps_multiplier = CaptureConstants.FPS_MULTIPLIER_IP_CAMERA if source_type == CaptureDeviceType.IpCamera else CaptureConstants.FPS_MULTIPLIER_DEFAULT
            sleep_seconds = 1.0 / (fps_multiplier * fps) - elapsed_seconds
            if sleep_seconds <= 0.0:
                sleep_seconds = self.capture_config.min_sleep_seconds
        else:
            sleep_seconds = self.capture_config.default_sleep_seconds
        
        return sleep_seconds

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
