import os


def _configure_direct_rtsp_proxy_resolver():
    """Keep LAN RTSP sources out of the system proxy discovery path."""
    os.environ.setdefault("GIO_USE_PROXY_RESOLVER", "dummy")


_configure_direct_rtsp_proxy_resolver()

try:
    import gi

    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib

    GSTREAMER_AVAILABLE = True
    if not Gst.is_initialized():
        Gst.init(None)
except ImportError:
    GSTREAMER_AVAILABLE = False
    Gst = None
    GLib = None

import numpy as np
import threading
import time
import datetime
from typing import Optional, List, Tuple, Any
from queue import Queue, Empty, Full
from .video_capture_base import VideoCaptureBase, CaptureDeviceType, EXEC_MODE_PROCESS
from .constants import CaptureConstants
from .exceptions import CaptureInitializationError, CaptureConnectionError
from ..core.frame import CaptureImage, Frame
from ..core.base_class import EvilEyeBase
from ..core.plugins import register_module

from evileye.video_recorder.recorder_base import SourceMeta
from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder

from .gstreamer_capture_recording import (
    GStreamerCaptureRecordingMixin,
    _RecordingFilesystemError,
)
from .gstreamer_capture_diagnostics import GStreamerCaptureDiagnosticsMixin
from .gstreamer_capture_pipeline import GStreamerCapturePipelineMixin
from .gstreamer_capture_frames import GStreamerCaptureFramesMixin


@register_module(
    "VideoCaptureGStreamer",
    kind="source",
    capabilities=("capture_source_backend", "preserves_source_metadata", "shared_frame_transport"),
    execution_modes=("thread", "process"),
    default_execution_mode="process",
)
class VideoCaptureGStreamer(
    GStreamerCaptureRecordingMixin,
    GStreamerCaptureDiagnosticsMixin,
    GStreamerCapturePipelineMixin,
    GStreamerCaptureFramesMixin,
    VideoCaptureBase,
):
    _recording_fs_error_logged = set()

    def __init__(self, config=None):
        super().__init__(plugin_config=config)
        self.pipeline = None
        self.appsink = None
        self.loop = None
        self.main_loop_thread = None
        # Use larger buffer for split streams to reduce overflows
        # Increased size for better performance with hardware decoders
        # Use deque-based queue for better performance (faster append/popleft)
        from collections import deque
        self.frame_buffer = Queue(maxsize=max(CaptureConstants.FRAME_BUFFER_SIZE, 10))
        # Pre-allocate deque for frame tracking (optimization)
        self._frame_buffer_deque = deque(maxlen=20)  # Track recent frame IDs for diagnostics
        self.last_frame = None
        # Use RLock for frame_lock to allow potential nested operations
        self.frame_lock = threading.RLock()
        # Use RLock for pipeline_lock to allow potential nested operations
        self.pipeline_lock = threading.RLock()
        self._release_lock = threading.Lock()
        self.gstreamer_available = GSTREAMER_AVAILABLE

        # Initialize GStreamer if available
        if self.gstreamer_available:
            if not Gst.is_initialized():
                Gst.init(None)
        else:
            self.logger.warning("GStreamer backend is unavailable")

        self.bus = None
        self._bus_handler_id = None
        self._fps_times = []  # rolling timestamps to estimate FPS as fallback

        # Recording-related attributes
        self._reconnecting = False
        self._rtsp_protocol = 'udp+tcp'  # Default: try UDP first, then TCP if UDP fails (GStreamer handles fallback)
        self._last_init_error = None
        self._init_time = None  # Track when pipeline was initialized to ignore early EOS
        self._appsink_handler_id = None  # Инициализация для избежания hasattr проверок
        # Performance metrics
        now = time.time()
        self._perf_stats_interval = 5.0
        self._perf_last_log = now
        self._perf_frame_count = 0
        self._perf_pull_total = 0.0
        self._perf_process_total = 0.0
        self._perf_pts_accum = 0.0
        self._perf_pts_count = 0
        self._perf_last_pts = None
        self._perf_frame_buffer_full = 0
        self._recording_queue_elem = None
        self._gst_continuous_recorder = None
        # Track callback frequency for diagnostics
        self._callback_count = 0
        self._callback_last_log = now

        # Error tracking for UDP stream errors
        self._udp_error_count = 0
        self._last_udp_error_time = None
        self._udp_error_reconnect_delay = 5.0  # Задержка перед реконнектом при UDP ошибках
        self._udp_error_threshold = 3  # Количество ошибок подряд перед реконнектом

        # Диагностические счетчики (явная инициализация вместо hasattr)
        self._get_call_count = 0
        self._get_call_last_log = now
        self._last_returned_frame_id = -1
        self._same_frame_count = 0

        # Reconnect backoff for video file branch in _grab_frames (same scheme as OpenCV)
        self._reconnect_attempt = 0

        # Recording: if output path is not writable/available, disable recording to avoid log flood
        self._recording_disabled_due_to_fs = False

        # Diagnostics for restarts / leak tracking
        self._restart_counter = 0
        self._last_restart_log_ts = 0.0

        # Timestamp of the last successfully pulled sample from appsink (wall clock).
        # This is more reliable than last_frame.time_stamp when split-stream frames are dropped,
        # or when buffer/last_frame references are in transition during restarts.
        self._last_sample_wall_ts: float = 0.0

        # VideoFile(loop_play) no-frames restart anti-flap/backoff.
        # Goal: avoid rebuilding pipelines every ~15s (can trigger driver/decoder memory growth).
        self._noframes_restart_last_ts = 0.0
        self._noframes_restart_consecutive = 0

        # Optional: force software decoding (disable NVDEC/Jetson HW decoders) to isolate driver-side leaks.
        # Can be set via env EVILEYE_GST_FORCE_SW_DECODER=1/true/yes/on, or params['force_sw_decoder']=true.
        self._force_sw_decoder: bool = False
        self._force_decodebin: bool = False
        try:
            import os as _os
            self._force_sw_decoder = _os.environ.get("EVILEYE_GST_FORCE_SW_DECODER", "").strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
            }
        except Exception:
            self._force_sw_decoder = False

        # Optional RSS trimming (glibc malloc_trim) can be expensive and cause restart stalls.
        # We run it asynchronously and rate-limit it when enabled.
        self._malloc_trim_last_ts: float = 0.0
        self._malloc_trim_lock = threading.Lock()

        # Subscriber notification worker (avoid spawning a thread per frame).
        # Initialized here so callbacks can safely access it even before any trims/restarts happen.
        self._notify_queue: Queue | None = Queue(maxsize=3)
        self._notify_stop = threading.Event()
        self._notify_thread: threading.Thread | None = None

    def calc_memory_consumption(self):
        """
        Override memory calculation to avoid GStreamer object issues.
        """
        try:
            # Exclude GStreamer objects from memory measurement as they cause issues
            safe_objects = {}
            for key, value in self.__dict__.items():
                if not (key.startswith('pipeline') or key.startswith('appsink') or
                        key.startswith('loop') or key.startswith('main_loop_thread')):
                    safe_objects[key] = value

            from pympler import asizeof
            import datetime
            self.memory_measure_results = asizeof.asizeof(safe_objects)
            self.memory_measure_time = datetime.datetime.now()
        except Exception as e:
            self.logger.warning(f"Could not measure memory consumption: {e}")
            self.memory_measure_results = 0
            self.memory_measure_time = datetime.datetime.now()

    def default(self):
        """
        Default implementation for EvilEyeBase.
        """
        pass

    def get_params_impl(self):
        """Return capture parameters including GStreamer-specific fields.

        Adds 'apiPreference' to ensure persistence in configs and propagates desired_fps.
        """
        params = super().get_params_impl()
        try:
            params['apiPreference'] = self.params.get('apiPreference', 'CAP_GSTREAMER')
            params['gstreamer_available'] = self.gstreamer_available
            params['loop_play'] = self.loop_play
            params['split'] = self.split_stream
            params['num_split'] = self.num_split
            params['src_coords'] = self.src_coords
        except Exception:
            params['apiPreference'] = 'CAP_GSTREAMER'
        return params

    def get_source_info(self) -> dict:
        """
        Get information about the video source.
        """
        info = {
            "source_type": self.source_type.value,
            "source_address": self.source_address,
            "is_working": self.is_working,
            "is_opened": self.is_opened(),
            "desired_fps": self.desired_fps
        }

        if self.source_type == CaptureDeviceType.IpCamera:
            info.update({
                "username": self.username,
                "has_password": bool(self.password),
                "pure_url": self.pure_url
            })

        return info

    def init(self):
        """
        Initialize the GStreamer capture.
        Returns True on success, False on failure.
        IP camera state transitions are asynchronous; bus errors and first-frame health
        determine whether the live source becomes operational.
        """
        if self.execution_mode == EXEC_MODE_PROCESS:
            return super().init()

        if not self.gstreamer_available:
            self.logger.error("GStreamer backend is unavailable")
            self.is_inited = False
            self.is_working = False
            raise CaptureInitializationError(
                "VideoCaptureGStreamer was selected but GStreamer is unavailable"
            )

        # RTSP negotiation is asynchronous and must not block initialization.
        if self.source_type == CaptureDeviceType.IpCamera:
            try:
                self._init_pipeline()
                self._start_main_loop()
                self.is_inited = True
                # Set is_working = True initially to allow frames to be processed
                # We'll verify it's actually working by checking for frames in _grab_frames
                self.is_working = True
                self.logger.info("GStreamer video capture initialized successfully")

                return True
            except CaptureInitializationError as e:
                self.logger.error("Failed to initialize GStreamer capture: %s", e)
                self.is_inited = False
                self.is_working = False
                self._last_init_error = e
                return False
            except Exception as e:
                hint = self.get_ip_camera_init_hint(e)
                error_msg = f"Failed to initialize GStreamer capture: {e}"
                if hint:
                    error_msg = f"{error_msg}. Hint: {hint}"
                self.logger.error(error_msg, exc_info=True)
                self.is_inited = False
                self.is_working = False
                # Store error for protocol switching logic
                self._last_init_error = e
                return False
        else:
            # For non-IP cameras, use timeout to prevent hanging
            import threading as _thr_init
            init_done = _thr_init.Event()
            init_ok = False
            init_err = None

            def _init_worker():
                nonlocal init_ok, init_err
                try:
                    self._init_pipeline()
                    self._start_main_loop()
                    init_ok = True
                except Exception as e:
                    init_err = e
                    init_ok = False
                finally:
                    init_done.set()

            init_thread = _thr_init.Thread(target=_init_worker, daemon=True)
            init_thread.start()

            # Wait up to 6 seconds for init
            if not init_done.wait(6.0):
                self.logger.error(f"GStreamer init timeout after 6s for {self.source_names}; pipeline may be stuck")
                # Force aggressive cleanup
                try:
                    with self.pipeline_lock:
                        if self.pipeline is not None:
                            try:
                                self.pipeline.set_state(Gst.State.NULL)
                            except Exception:
                                pass
                            self.pipeline = None
                        self.bus = None
                        self.appsink = None
                except Exception:
                    pass
                self.is_inited = False
                self.is_working = False
                return False

            if init_err is not None:
                self.logger.error(f"Failed to initialize GStreamer capture: {init_err}")
                self.is_inited = False
                self.is_working = False
                return False

            if init_ok:
                self.is_inited = True
                self.is_working = True
                self.logger.info("GStreamer video capture initialized successfully")
                return True
            else:
                self.is_inited = False
                self.is_working = False
                return False

    def init_impl(self, **kwargs):
        """
        Implementation of EvilEyeBase init_impl.
        """
        return self.init()

    def is_opened(self) -> bool:
        """
        Check if capture is opened and working.
        """
        return self.is_working and self.pipeline is not None

    def release(self) -> None:
        """Release resources through the shared, idempotent pipeline teardown."""
        # Serialize callers: returning early while another teardown is still
        # stopping a native pipeline would let reconnect initialize it too soon.
        self._release_lock.acquire()
        try:
            self._teardown_pipeline("release", join_main_loop=True)
            self.is_inited = False
            self.is_working = False
            self.logger.info("GStreamer video capture released")
        except Exception as e:
            self.logger.error("Error releasing GStreamer capture: %s", e)
        finally:
            self._release_lock.release()

    def release_impl(self):
        """
        Implementation of EvilEyeBase release_impl.
        """
        self.release()

    def reset_impl(self):
        """
        Implementation of EvilEyeBase reset_impl.
        """
        self.release()
        self.is_inited = False
        self.is_working = False

    def set_params_impl(self):
        """
        Implementation of EvilEyeBase set_params_impl.
        """
        super().set_params_impl()

    def start(self):
        """
        Override start() to always launch grab/retrieve threads, even if init() failed.
        This allows reconnect logic to work from the start.
        """
        if self.execution_mode == EXEC_MODE_PROCESS:
            # Process mode: frames leave via mp_worker_capture + queue_policy.put_drop_oldest.
            super().start()
            return

        self.run_flag = True
        # Always start threads, even if not initialized - reconnect logic will handle it
        self.grab_thread = threading.Thread(target=self._grab_frames, daemon=True)
        self.retrieve_thread = threading.Thread(target=self._retrieve_frames, daemon=True)
        self.grab_thread.start()
        self.retrieve_thread.start()
        # Start recording if configured (for OpenCV backend, not GStreamer - GStreamer uses tee)
        # For GStreamer, recording is integrated in pipeline via tee
        try:
            # `enabled` is a master switch. Continuous recording must be explicitly enabled.
            continuous_enabled = bool(
                self.recording_params
                and self.recording_params.enabled
                and self.recording_params.continuous_recording_enabled
            )
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
                        source_type=str(self.source_type.value),
                        width=None,
                        height=None,
                        fps=self.source_fps,
                        username=getattr(self, 'username', None),
                        password=getattr(self, 'password', None),
                        source_names=getattr(self, 'source_names', None),
                        source_ids=getattr(self, 'source_ids', None),
                    )
                    try:
                        if self.recorder_manager:
                            self.recorder_manager.start_recording(meta, self.recording_params)
                    except Exception as e:
                        self.logger.error(f"Failed to start recording: {e}")
        except Exception as e:
            self.logger.debug(f"Error starting recording: {e}")
