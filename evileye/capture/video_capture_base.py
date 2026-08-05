import copy
import datetime
import time
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
from ..core.frame_transport import FrameHandle, SharedFrameTransport
from .constants import CaptureConstants, CaptureConfig
from .queue_utils import DropOldestQueue

from ..core.processor_base import (
    DEFAULT_EXECUTION_MODE,
    EXEC_MODE_PROCESS,
    EXEC_MODE_THREAD,
)


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
        self.execution_mode = DEFAULT_EXECUTION_MODE
        self._mp_control = None
        self._capture_dispatch_thread: threading.Thread | None = None
        self._frame_transport = SharedFrameTransport()
        # Process mode: parent tracks frame flow from child worker (is_working lives in worker).
        self._mp_last_frame_mono: float = 0.0
        self._mp_worker_started_mono: float = 0.0

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
        if (
            self.execution_mode == EXEC_MODE_PROCESS
            and not self.get_init_flag()
            and not self._running_inside_mp_worker()
        ):
            self.is_inited = self._init_process_mode()
            return self.is_inited
        return super().init(**kwargs)

    @staticmethod
    def _running_inside_mp_worker() -> bool:
        """True when already inside an MpControl worker (no nested spawn)."""
        try:
            import multiprocessing as mp

            return mp.parent_process() is not None
        except Exception:
            return False

    def get(self) -> list[CaptureImage]:
        captured_images: list[CaptureImage] = []
        if self.get_init_flag():
            if self.execution_mode == EXEC_MODE_PROCESS:
                captured_images = self._get_frames_from_queue()
            else:
                captured_images = self.get_frames_impl()
        return captured_images

    def _get_frames_from_queue(self) -> list[CaptureImage]:
        """Read from frames_queue (process mode).

        Drains all immediately available items but returns at most one frame per
        ``source_id`` per pipeline tick. Extra frames for the same source are
        re-queued so split capture (e.g. Cam1+Cam2 on one worker) matches
        thread-mode GStreamer behaviour, which returns every split region per
        ``get_frames_impl()`` call.
        """
        frames: list[CaptureImage] = []
        seen_source_ids: set[int] = set()
        deferred: list[CaptureImage] = []
        max_drain = max(32, int(self.capture_config.queue_size or 2) * 4)

        for _ in range(max_drain):
            try:
                frame = self.frames_queue.get_nowait()
            except Empty:
                break
            if frame is None:
                continue
            sid = getattr(frame, "source_id", None)
            if sid is not None:
                try:
                    sid = int(sid)
                except (TypeError, ValueError):
                    sid = None
            if sid is not None and sid in seen_source_ids:
                deferred.append(frame)
                continue
            if sid is not None:
                seen_source_ids.add(sid)
            frames.append(frame)

        for frame in deferred:
            try:
                self.frames_queue.put_nowait(frame)
            except Exception:
                try:
                    self.frames_queue.put(frame)
                except Exception:
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
            ok, reason = self.recording_params.check_out_dir_writable()
            if not ok:
                self.logger.error(
                    "Recording disabled for %s: out_dir is not writable (%s): %s",
                    meta.source_name,
                    getattr(self.recording_params, "out_dir", None),
                    reason,
                )
                return
        except Exception as exc:
            self.logger.warning(
                "Could not verify recording out_dir for %s: %s",
                meta.source_name,
                exc,
            )

        try:
            url = self._sanitize_url_for_logging(str(meta.source_address))
            self.logger.info(
                "Starting recording: backend=%s name=%s url=%s out_dir=%s",
                backend,
                meta.source_name,
                url,
                getattr(self.recording_params, "out_dir", None),
            )
        except Exception as e:
            self.logger.error(f"Error logging recording start: {e}")

        try:
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

    def _recording_config_dict(self) -> dict | None:
        """Serialize active recording settings for MP worker / get_params round-trip."""
        if isinstance(self.params, dict):
            record_cfg = self.params.get("record")
            if isinstance(record_cfg, dict) and record_cfg:
                return dict(record_cfg)
        if not self.recording_params:
            return None
        rp = self.recording_params
        return {
            "enabled": rp.enabled,
            "continuous_recording_enabled": rp.continuous_recording_enabled,
            "event_recording_enabled": rp.event_recording_enabled,
            "event_pre_seconds": rp.event_pre_seconds,
            "event_post_seconds": rp.event_post_seconds,
            "event_buffer_fps": rp.event_buffer_fps,
            "container": rp.container,
            "segment_length_sec": rp.segment_length_sec,
            "retention_days": rp.retention_days,
            "min_free_space_pct": rp.min_free_space_pct,
            "min_file_size_kb": rp.min_file_size_kb,
            "out_dir": rp.out_dir,
            "filename_tmpl": rp.filename_tmpl,
            "validate_video_integrity": rp.validate_video_integrity,
            "video_validation_timeout": rp.video_validation_timeout,
        }

    def _worker_capture_params(self) -> dict:
        """Params passed to MpWorkerCapture; must include record for child-process recording."""
        params = dict(self.params or {})
        record_cfg = self._recording_config_dict()
        if record_cfg is not None:
            params["record"] = record_cfg
        return params

    def _init_process_mode(self) -> bool:
        """Initialise MpControl + MpWorkerCapture for process-based capture."""
        from ..core.mp_control import MpControl, parse_mp_restart_policy
        from .mp_worker_capture import MpWorkerCapture
        # Capture init failures use exit code 2; never restart-loop by default.
        restart_on_exit, no_restart_exit_codes = parse_mp_restart_policy(
            self.params,
            default_restart_on_exit=False,
            default_no_restart_exit_codes={2, -15},
        )
        no_restart_exit_codes.add(2)

        self._mp_control = MpControl(
            max_input_size=4,
            max_output_size=max(2, int(self.capture_config.queue_size or 2)),
            name=f"capture-{'_'.join(str(s) for s in (self.source_ids or [0]))}",
            restart_on_exit=restart_on_exit,
            no_restart_exit_codes=no_restart_exit_codes,
        )
        worker = self._mp_control.add_worker(MpWorkerCapture)
        worker.set_params(self._worker_capture_params())
        self._mp_control.start()
        self._mp_worker_started_mono = time.monotonic()
        self._mp_last_frame_mono = 0.0
        self.logger.info("Capture initialised in PROCESS mode")
        return True

    def sync_process_mode_health(self) -> None:
        """Refresh parent ``is_working`` for process-mode capture (runtime snapshot / web health).

        The real capture backend runs in a child process; without this sync the parent proxy
        stays at the default ``is_working=False`` and web marks every camera as reconnecting.
        """
        if self.execution_mode != EXEC_MODE_PROCESS or self._mp_control is None:
            return
        try:
            if not self._mp_control.is_alive():
                self.is_working = False
                return
        except Exception:
            self.is_working = False
            return

        timeout_sec = float(
            getattr(self.capture_config, "frame_timeout_seconds", None)
            or CaptureConstants.FRAME_TIMEOUT_SECONDS
        )
        now_mono = time.monotonic()

        if self._mp_last_frame_mono > 0.0:
            if (now_mono - self._mp_last_frame_mono) <= timeout_sec:
                self.is_working = True
            elif self.source_type == CaptureDeviceType.IpCamera:
                self.is_working = False
            return

        # Worker alive, no frames yet: optimistic during init grace, then down for IP cameras.
        grace_sec = float(
            getattr(self.capture_config, "init_grace_period_seconds", None)
            or CaptureConstants.INIT_GRACE_PERIOD_SECONDS
        )
        started_mono = self._mp_worker_started_mono or now_mono
        if (now_mono - started_mono) <= grace_sec:
            self.is_working = True
        elif self.source_type == CaptureDeviceType.IpCamera:
            self.is_working = False

    def _touch_process_mode_frame_activity(self) -> None:
        """Mark capture healthy when a frame arrives from the MP worker."""
        if self.execution_mode != EXEC_MODE_PROCESS:
            return
        self._mp_last_frame_mono = time.monotonic()
        self.is_working = True
        self.is_inited = True
        self.last_frame_time = datetime.datetime.now()

    def _capture_dispatch_loop(self) -> None:
        """Read CaptureImage objects from child process and put them into frames_queue."""
        while self.run_flag:
            try:
                payload = self._mp_control.get(timeout=0.5)
            except Exception:
                self._mark_finished_if_worker_stopped()
                continue
            frame = self._unpack_capture_payload(payload)
            if frame is None:
                self._mark_finished_if_worker_stopped()
                continue
            self._touch_process_mode_frame_activity()
            try:
                self.frames_queue.put(frame)
            except Exception:
                pass

    def _unpack_capture_payload(self, payload):
        """Convert descriptor payload from capture worker to CaptureImage."""
        if isinstance(payload, dict) and "frame_handle" in payload:
            try:
                handle = payload.get("frame_handle")
                if not isinstance(handle, FrameHandle):
                    return None
                meta = payload.get("frame_meta", {}) or {}
                frame = Frame()
                frame.source_id = meta.get("source_id")
                frame.frame_id = meta.get("frame_id")
                frame.current_video_frame = meta.get("current_video_frame")
                frame.current_video_position = meta.get("current_video_position")
                frame.source_video_duration = meta.get("source_video_duration")
                frame.time_stamp = meta.get("time_stamp")
                frame.image = self._frame_transport.consume_frame(handle)
                return frame
            except Exception:
                return None
        return payload

    def _mark_finished_if_worker_stopped(self) -> None:
        """Mark source as finished when process-mode worker exited and queue is drained."""
        try:
            if self._mp_control is None:
                return
            if self.finished:
                return
            if self._mp_control.is_alive():
                return
            if not self._mp_control.output_empty():
                return
            self.finished = True
            self.is_working = False
            try:
                self.logger.info(
                    "Capture worker stopped and output queue drained; marking source as finished"
                )
            except Exception:
                pass
        except Exception:
            pass

    def start(self) -> None:
        """Start video capture threads and recording."""
        if self.execution_mode == EXEC_MODE_PROCESS and self._mp_control is not None:
            self.finished = False
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
                # Keep source shutdown bounded: ProcessorBase stop timeout is 8s.
                # Capture stop path must complete faster to avoid container-level timeouts.
                self._mp_control.stop(timeout=2.0)
            except Exception:
                pass
            self._mp_control = None
            if self._capture_dispatch_thread is not None:
                try:
                    self._capture_dispatch_thread.join(timeout=1.0)
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

    def force_stop(self) -> None:
        """Aggressive emergency stop used when normal stop exceeds timeout."""
        self.run_flag = False
        self.stop_event.set()
        try:
            if self._mp_control is not None:
                self._mp_control.stop(timeout=0.5)
        except Exception:
            pass
        self._mp_control = None
        try:
            if self._capture_dispatch_thread is not None:
                self._capture_dispatch_thread.join(timeout=0.2)
        except Exception:
            pass
        self._capture_dispatch_thread = None
        self._cleanup_queue()

    def set_params_impl(self) -> None:
        self.release()
        self.execution_mode = self.params.get('execution_mode', DEFAULT_EXECUTION_MODE)
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
        record_cfg = self._recording_config_dict()
        if record_cfg is not None:
            params['record'] = record_cfg
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

        reconstructed_url = url_parsed_info._replace(
            netloc=f"{processed_username}:{processed_password}@{url_parsed_info.hostname}")
        return reconstructed_url.geturl()

    def get_ip_camera_init_hint(self, last_error: Exception | str | None = None) -> str:
        """Return a human-readable hint for common RTSP configuration mistakes.

        Hints are attached only when the failure looks RTSP/GStreamer-related,
        so filesystem/import bugs are not misdiagnosed as bad camera URLs.
        """
        if self.source_type != CaptureDeviceType.IpCamera:
            return ""

        if last_error is not None:
            err_name = type(last_error).__name__ if isinstance(last_error, BaseException) else ""
            err_text = f"{err_name}: {last_error}".lower()
            non_rtsp_markers = (
                "permission denied",
                "not defined",
                "not writable",
                "recordingfilesystem",
                "no such file",
                "read-only",
                "disk quota",
                "nameerror",
                "filesystem",
            )
            if any(tok in err_text for tok in non_rtsp_markers):
                return ""
            rtsp_markers = (
                "rtsp",
                "gst",
                "pipeline",
                "candidate",
                "appsink",
                "unauthorized",
                "401",
                "403",
                "timeout",
                "connection refused",
                "connection reset",
                "not-negotiated",
                "could not connect",
            )
            if not any(tok in err_text for tok in rtsp_markers):
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
            region = src_image[y:y + h, x:x + w].copy()

            # Get source ID for this split
            source_id = self.source_ids[stream_cnt] if self.source_ids and stream_cnt < len(
                self.source_ids) else stream_cnt

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
