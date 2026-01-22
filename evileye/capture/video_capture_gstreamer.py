import cv2
import numpy as np
import threading
import time
import datetime
from typing import Optional, List, Tuple, Any
from queue import Queue, Empty, Full
from .video_capture_base import VideoCaptureBase, CaptureDeviceType
from .constants import CaptureConstants
from .exceptions import CaptureInitializationError, CaptureConnectionError
from ..core.frame import CaptureImage, Frame
from ..core.base_class import EvilEyeBase

# Try to import GStreamer, fallback to OpenCV if not available
try:
    import gi
    gi.require_version('Gst', '1.0')
    from gi.repository import Gst, GLib
    GSTREAMER_AVAILABLE = True
except ImportError:
    GSTREAMER_AVAILABLE = False
    Gst = None
    GLib = None


@EvilEyeBase.register("VideoCaptureGStreamer")
class VideoCaptureGStreamer(VideoCaptureBase):
    """
    GStreamer-based video capture implementation.
    Supports various input sources including IP cameras, video files, and devices.
    """
    
    def __init__(self):
        super().__init__()
        self.pipeline = None
        self.appsink = None
        self.loop = None
        self.main_loop_thread = None
        # Use larger buffer for split streams to reduce overflows
        # Increased size for better performance with hardware decoders
        self.frame_buffer = Queue(maxsize=max(CaptureConstants.FRAME_BUFFER_SIZE, 10))
        self.last_frame = None
        # Use RLock for frame_lock to allow potential nested operations
        self.frame_lock = threading.RLock()
        # Use RLock for pipeline_lock to allow potential nested operations
        self.pipeline_lock = threading.RLock()
        self.gstreamer_available = GSTREAMER_AVAILABLE
        
        # Initialize GStreamer if available
        if self.gstreamer_available:
            if not Gst.is_initialized():
                Gst.init(None)
        else:
            self.logger.warning("GStreamer not available, falling back to OpenCV")
        
        self.bus = None
        self._fps_times = []  # rolling timestamps to estimate FPS as fallback
        
        # Recording-related attributes
        self._recording_elements = None
        self._recording_check_thread = None
        self._recording_check_stop = False
        self._recording_out_dir = None
        self._recording_checked_files = set()
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
        # Track callback frequency for diagnostics
        self._callback_count = 0
        self._callback_last_log = now

    # Debug stack dump removed
    
    def _mask_credentials_in_pipeline(self, pipeline_str: str) -> str:
        """
        Mask credentials (username and password) in pipeline string for logging.
        Replaces user-id=... and user-pw=... with user-id=**** and user-pw=****
        Also masks credentials in RTSP URLs (rtsp://user:pass@host → rtsp://****:****@host)
        """
        if not pipeline_str:
            return pipeline_str
        try:
            import re
            # Mask user-id="username" or user-id=username
            pipeline_str = re.sub(r'user-id=["\']?([^"\'\s]+)["\']?', r'user-id="****"', pipeline_str)
            # Mask user-pw="password" or user-pw=password
            pipeline_str = re.sub(r'user-pw=["\']?([^"\'\s]+)["\']?', r'user-pw="****"', pipeline_str)
            # Mask credentials in RTSP URL: rtsp://user:pass@host → rtsp://****:****@host
            pipeline_str = re.sub(r'rtsp://[^:@/]+:[^@]+@', 'rtsp://****:****@', pipeline_str)
            # Mask credentials in RTSP URL without password: rtsp://user@host → rtsp://****@host
            pipeline_str = re.sub(r'rtsp://[^:@/]+@', 'rtsp://****@', pipeline_str)
        except Exception:
            pass
        return pipeline_str
    
    def _gst_has(self, element_name: str) -> bool:
        """Check if GStreamer element factory exists."""
        try:
            return self.gstreamer_available and Gst.ElementFactory.find(element_name) is not None
        except Exception:
            return False
    
    def _build_pipeline(self) -> str:
        """
        Build GStreamer pipeline based on source type and parameters.
        """
        if self.source_type == CaptureDeviceType.IpCamera:
            # IP Camera pipeline - use explicit codec paths like in api-refactoring
            # Try H265 first, then H264 as fallback (handled by pipeline candidates in _init_pipeline)
            # Use UDP protocol by default, but allow TCP fallback if UDP fails (protocols=udp+tcp)
            # This allows GStreamer to try UDP first, then fallback to TCP if UDP doesn't work
            protocol = getattr(self, '_rtsp_protocol', 'udp+tcp')  # Try UDP first, then TCP if UDP fails
            if self.username and self.password:
                # Try H265 first (more common for modern cameras)
                pipeline = f"rtspsrc location={self.source_address} user-id={self.username} user-pw={self.password} protocols={protocol} ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert"
            else:
                # Try H264 first (more compatible)
                pipeline = f"rtspsrc location={self.source_address} protocols={protocol} ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
            
        elif self.source_type == CaptureDeviceType.VideoFile:
            # Video file pipeline - optimized with hardware acceleration support
            # Step 1: Try hardware decoder (NVDEC for NVIDIA GPUs)
            # Step 2: Fallback to explicit software decoder (faster than decodebin)
            # Step 3: Last resort: decodebin (supports all formats)
            
            file_ext = str(self.source_address).lower()
            is_mp4 = file_ext.endswith('.mp4')
            is_mkv = file_ext.endswith('.mkv')
            
            # Check for NVIDIA hardware decoder (NVDEC)
            use_nvdec = (
                self._gst_has('nvh264dec') and
                is_mp4  # NVDEC works best with MP4/H.264
            )
            
            # Check for Jetson hardware decoder (older API)
            use_nvv4l2 = (
                self._gst_has('nvv4l2decoder') and
                self._gst_has('nvvidconv') and
                is_mp4
            )
            
            if use_nvdec:
                # Use NVDEC hardware decoder (RTX/GTX series)
                # This is the fastest path for H.264/MP4 files on NVIDIA GPUs
                pipeline = (
                    f"filesrc location={self.source_address} ! qtdemux ! h264parse ! nvh264dec "
                    f"! videoconvert"
                )
                self.logger.info(f"Using NVDEC hardware decoder for {self.source_names}")
            elif use_nvv4l2:
                # Use Jetson hardware decoder (older API)
                pipeline = (
                    f"filesrc location={self.source_address} ! qtdemux ! h264parse ! nvv4l2decoder "
                    f"! nvvidconv ! video/x-raw(memory:NVMM),format=BGRx ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert"
                )
                self.logger.info(f"Using Jetson hardware decoder for {self.source_names}")
            elif is_mp4:
                # Use explicit software decoder for MP4 (faster than decodebin)
                # qtdemux ! h264parse ! avdec_h264 is more efficient than decodebin
                if self._gst_has('qtdemux') and self._gst_has('h264parse') and self._gst_has('avdec_h264'):
                    pipeline = (
                        f"filesrc location={self.source_address} ! qtdemux ! h264parse ! avdec_h264 ! videoconvert"
                    )
                    self.logger.info(f"Using explicit H.264 decoder for {self.source_names}")
                else:
                    # Fallback to decodebin if explicit decoder not available
                    pipeline = f"filesrc location={self.source_address} ! decodebin name=dec ! videoconvert"
            else:
                # For other formats, use decodebin (supports all codecs)
                pipeline = f"filesrc location={self.source_address} ! decodebin name=dec ! videoconvert"
                   
            
        elif self.source_type == CaptureDeviceType.Device:
            # USB/Device camera pipeline
            device_id = self.source_address if self.source_address.isdigit() else "0"
            pipeline = f"v4l2src device=/dev/video{device_id} ! videoconvert"
            
        elif self.source_type == CaptureDeviceType.ImageSequence:
            # Image sequence pipeline - prefer explicit caps/decoder to avoid typefind issues
            pattern = str(self.source_address)
            is_pattern = any(ch in pattern for ch in ['%', '*', '?'])
            if not is_pattern:
                # Treat as directory; append wildcard to pick all images
                if pattern.endswith("/"):
                    pattern = f"{pattern}frame_%05d.jpg"
                else:
                    pattern = f"{pattern}/frame_%05d.jpg"
            # Determine decoder/caps from extension if possible
            decoder = "decodebin"
            caps_str = None
            import os
            _, ext = os.path.splitext(pattern.lower())
            fps_num, fps_den = (15, 1)
            if self.desired_fps and self.desired_fps > 0:
                fps = float(self.desired_fps)
                if abs(fps - round(fps)) < 1e-6:
                    fps_num, fps_den = int(round(fps)), 1
                else:
                    fps_num, fps_den = int(round(fps * 1001)), 1001
            if ext in {".jpg", ".jpeg"}:
                caps_str = f"image/jpeg,framerate={fps_num}/{fps_den}"
                decoder = "jpegdec"
            elif ext == ".png":
                caps_str = f"image/png,framerate={fps_num}/{fps_den}"
                decoder = "pngdec"
            elif ext == ".bmp":
                caps_str = f"image/bmp,framerate={fps_num}/{fps_den}"
                decoder = "decodebin"
            # Build pipeline with caps when known to avoid gst_type_find errors
            if caps_str:
                pipeline = (
                    f"multifilesrc location={pattern} loop=false do-timestamp=true caps=\"{caps_str}\" "
                    f"! {decoder} ! videoconvert"
                )
            else:
                pipeline = (
                    f"multifilesrc location={pattern} loop=false do-timestamp=true "
                    f"! decodebin ! videoconvert"
                )
        
        else:
            raise ValueError(f"Unsupported source type: {self.source_type}")
        
        # Add common pipeline end - simplified
        # Apply desired FPS if requested using videorate (before format caps/appsink)
        # NOTE: For VideoFile, videorate can slow down playback unnecessarily.
        # Only apply videorate for live sources (IpCamera) or when explicitly desired.
        if self.desired_fps and self.desired_fps > 0:
            # For VideoFile, videorate may unnecessarily slow down playback
            # Only apply if it's a live source or explicitly needed
            if self.source_type != CaptureDeviceType.VideoFile:
                try:
                    # Convert to fraction (prefer integer; fallback to 1001 base)
                    fps = float(self.desired_fps)
                    if abs(fps - round(fps)) < 1e-6:
                        num, den = int(round(fps)), 1
                    else:
                        # Use 1001 denominator for common NTSC-like framerates
                        num, den = int(round(fps * 1001)), 1001
                    # Limit to desired FPS without upsampling (no capsfilter forcing framerate)
                    # videorate max-rate drops frames if source faster; if slower, it passes through
                    pipeline += f" ! videorate max-rate={num} drop-only=true"
                except Exception:
                    # If anything goes wrong, skip forcing fps
                    pass
        # Determine sync mode: false for VideoFile (no need to sync with clock), true for live sources
        sync_mode = "false" if self.source_type == CaptureDeviceType.VideoFile else "true"
        
        # If continuous recording is enabled, use tee to split stream: one to appsink, one to recording
        continuous_enabled = (self.recording_params and 
                              (self.recording_params.continuous_recording_enabled or 
                               (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
        if continuous_enabled:
            # Use tee to split stream
            # NOTE: tee requires queues on each branch to avoid blocking
            pipeline += " ! tee name=t"
            # Branch 1: to appsink for capture
            # For VideoFile, use minimal queue (just enough for tee to work)
            if self.source_type == CaptureDeviceType.VideoFile:
                pipeline += f" t. ! queue max-size-buffers=2 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=3 drop=true"
            else:
                # For live sources, keep larger queue for isolation
                pipeline += f" t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=3 drop=true"
            # Branch 2: to recording (will be connected after pipeline creation)
            pipeline += " t. ! queue name=recording_queue"
        else:
            # No recording - direct to appsink
            # For VideoFile, no queue needed (no tee)
            if self.source_type == CaptureDeviceType.VideoFile:
                pipeline += f" ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=3 drop=true"
            else:
                # For live sources, keep queue for isolation
                pipeline += f" ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync={sync_mode} max-buffers=3 drop=true"
        
        return pipeline
    
    def _extract_frame_data(self, sample: Any) -> Tuple[np.ndarray, int, int, Optional[float]]:
        """Extract frame data from GStreamer sample.
        
        Args:
            sample: GStreamer sample object
            
        Returns:
            Tuple of (frame_data, width, height, pts_value)
            
        Raises:
            Exception: If frame extraction fails
        """
        buffer = sample.get_buffer()
        caps = sample.get_caps()
        pts_value = buffer.pts if buffer else None
        
        # Get frame dimensions
        structure = caps.get_structure(0)
        width = structure.get_int("width")[1]
        height = structure.get_int("height")[1]
        
        # Try to get FPS from caps if not set
        if self.source_fps is None and structure is not None:
            try:
                if structure.has_field("framerate"):
                    num, den = structure.get_fraction("framerate")
                    if den != 0:
                        self.source_fps = float(num) / float(den)
            except Exception:
                pass
        
        # Map buffer and extract frame data
        map_info = None
        try:
            success, map_info = buffer.map(Gst.MapFlags.READ)
            if not success:
                raise RuntimeError("Failed to map buffer")
            
            # Convert buffer to numpy array
            frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
            frame_data = frame_data.reshape((height, width, 3))
            
            # Copy is necessary: GStreamer buffer is read-only and may be reused
            # Copy once here to avoid issues with split_stream, recording, and subscriber processing
            frame_data = frame_data.copy()
            
            return frame_data, width, height, pts_value
        finally:
            # Always unmap buffer to prevent memory leaks
            if map_info is not None:
                try:
                    buffer.unmap(map_info)
                except Exception:
                    pass

    def _process_gstreamer_frame_metadata(self, buffer, frame_data: np.ndarray) -> tuple[int | None, float | None]:
        """Process frame metadata for GStreamer (video position, frame number).
        
        Args:
            buffer: GStreamer buffer object
            frame_data: Extracted frame data
            
        Returns:
            Tuple of (current_video_frame, current_video_position)
        """
        current_video_frame = None
        current_video_position = None
        
        if self.source_type == CaptureDeviceType.VideoFile:
            try:
                # Prefer buffer PTS for accurate position
                pts_ns = buffer.pts
                if pts_ns is not None and pts_ns != Gst.CLOCK_TIME_NONE and pts_ns >= 0:
                    self.video_current_position = float(pts_ns) / 1e6  # ms
                else:
                    ok, pos_ns = self.pipeline.query_position(Gst.Format.TIME)
                    if ok and pos_ns is not None and pos_ns >= 0:
                        self.video_current_position = float(pos_ns) / 1e6  # milliseconds
                    else:
                        self.video_current_position = None
            except Exception:
                self.video_current_position = None
            
            # Approximate current frame if fps is known
            if self.source_fps and self.video_current_position is not None:
                self.video_current_frame = int((self.video_current_position / 1000.0) * self.source_fps)
            else:
                if self.video_current_frame is None:
                    self.video_current_frame = 0
                else:
                    self.video_current_frame += 1
            current_video_frame = self.video_current_frame
            current_video_position = self.video_current_position
        
        return current_video_frame, current_video_position

    def _store_frame(self, capture_image: CaptureImage, is_split: bool = False) -> None:
        """Store frame in buffer and update counters.
        
        Args:
            capture_image: CaptureImage object to store
            is_split: Whether this is a split stream frame
        """
        with self.frame_lock:
            if is_split:
                # For split streams, store in frame_buffer
                # Optimized: Try to add frame, if full, remove multiple old frames to make room
                # This reduces buffer overflows by being more aggressive about clearing old frames
                try:
                    self.frame_buffer.put(capture_image, block=False)
                except Full:
                    self._perf_frame_buffer_full += 1
                    # Remove multiple old frames to make room (more aggressive clearing)
                    frames_removed = 0
                    max_removals = min(3, self.frame_buffer.qsize())  # Remove up to 3 old frames
                    while frames_removed < max_removals:
                        try:
                            old_frame = self.frame_buffer.get_nowait()
                            # Explicitly free memory from old frame
                            if old_frame is not None:
                                old_frame.image = None
                            old_frame = None
                            frames_removed += 1
                        except Empty:
                            break
                    # Try to add new frame
                    try:
                        self.frame_buffer.put_nowait(capture_image)
                    except Full:
                        # If still full after clearing, drop the new frame (shouldn't happen often)
                        self.logger.debug(f"Frame buffer still full after clearing {frames_removed} frames, dropping frame for source {capture_image.source_id}")
            else:
                # For single stream, store as last_frame
                # Free memory from old last_frame AFTER storing new one
                # Since get_frames_impl now creates copies, it's safe to free old frame
                old_last_frame = self.last_frame
                self.last_frame = capture_image
                # Free old frame memory (safe now because get_frames_impl creates copies)
                if old_last_frame is not None:
                    old_last_frame.image = None
            self.frame_id_counter += 1

    def _notify_subscribers_async(self, capture_images: List[CaptureImage]) -> None:
        """Notify subscribers asynchronously about new frames.
        
        Optimized: Only notify if there are subscribers, and use a single thread for all notifications.
        
        Args:
            capture_images: List of CaptureImage objects to notify about
        """
        # Early exit if no subscribers - avoid unnecessary work
        if not self.subscribers:
            return
        
        # Use a single thread for all notifications to reduce overhead
        def _notify_all():
            try:
                for capture_image in capture_images:
                    for sub in self.subscribers:
                        try:
                            if callable(sub):
                                sub(capture_image)
                            else:
                                if hasattr(sub, 'process_frame'):
                                    sub.process_frame(capture_image)
                                elif hasattr(sub, 'update'):
                                    sub.update()
                        except Exception as ex:
                            try:
                                self.logger.error(f"Error notifying subscriber {type(sub)}: {ex}")
                            except Exception:
                                pass
            except Exception as ex:
                try:
                    self.logger.error(f"Error in subscriber notification thread: {ex}")
                except Exception:
                    pass
        
        # Start single thread for all notifications
        threading.Thread(target=_notify_all, daemon=True).start()

    def _on_new_sample(self, appsink: Any) -> Any:
        """
        Callback for new frame from GStreamer pipeline.
        """
        pull_duration = 0.0
        try:
            pull_start = time.perf_counter()
            sample = appsink.emit("pull-sample")
            pull_duration = time.perf_counter() - pull_start
            if sample:
                processing_start = time.perf_counter()
                # Extract frame data first (before checking is_working)
                # This allows us to process the frame even if is_working is False initially
                try:
                    frame_data, width, height, pts_value = self._extract_frame_data(sample)
                except Exception as e:
                    process_time = time.perf_counter() - processing_start
                    self._record_perf_metrics(pull_duration, process_time, None)
                    self.logger.error(f"Failed to extract frame data: {e}")
                    return Gst.FlowReturn.ERROR
                
                # Process frame metadata
                buffer = sample.get_buffer()
                current_video_frame, current_video_position = self._process_gstreamer_frame_metadata(buffer, frame_data)
                
                # Maintain rolling FPS estimate as fallback (optimized: only update when needed)
                now = time.time()
                # Only update FPS estimate if not already set or if we need to recalculate
                if self.source_fps is None:
                    self._fps_times.append(now)
                    if len(self._fps_times) > 30:
                        self._fps_times.pop(0)
                    if len(self._fps_times) >= 2:
                        dt = self._fps_times[-1] - self._fps_times[0]
                        if dt > 0:
                            self.source_fps = (len(self._fps_times) - 1) / dt
                
                # Track callback frequency for diagnostics (optimized: only log periodically)
                self._callback_count += 1
                if now - self._callback_last_log >= 5.0:
                    source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(self.source_address)
                    callback_fps = self._callback_count / (now - self._callback_last_log)
                    self.logger.debug(f"Capture callback [{source_label}]: {callback_fps:.2f} callbacks/sec, callback_count={self._callback_count}")
                    self._callback_count = 0
                    self._callback_last_log = now
                
                # Create CaptureImage objects
                if self.split_stream and self.src_coords and self.num_split > 0:
                    try:
                        capture_images = self._handle_split_stream(
                            src_image=frame_data,
                            frame_id=self.frame_id_counter,
                            timestamp=now,
                            current_video_frame=current_video_frame,
                            current_video_position=current_video_position
                        )
                    except Exception as e:
                        self.logger.error(f"Error in _handle_split_stream for {self.source_names}: {e}", exc_info=True)
                        capture_images = []
                    
                    # Mark as working when we receive first valid frame after init
                    # IMPORTANT: For split streams, we mark as working even if capture_images is empty initially
                    # This allows subsequent frames to be processed
                    if self._init_time and not self.is_working:
                        if (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                            if capture_images:
                                self.logger.info(f"First frame received {(now - self._init_time):.1f}s after init - marking as working")
                                self.is_working = True
                            else:
                                # Even if split failed, we received a frame from GStreamer
                                # Mark as working to allow subsequent frames to be processed
                                self.logger.warning(f"First frame received but split returned empty for {self.source_names} - marking as working anyway")
                                self.is_working = True
                    
                    # If still not working after init grace period, skip frame
                    if not self.is_working:
                        process_time = time.perf_counter() - processing_start
                        self._record_perf_metrics(pull_duration, process_time, pts_value)
                        return Gst.FlowReturn.OK
                    
                    # Store frames
                    if capture_images:
                        for img in capture_images:
                            self._store_frame(img, is_split=True)
                        # Store first frame as last_frame for compatibility
                        with self.frame_lock:
                            self.last_frame = capture_images[0]
                        # Notify subscribers asynchronously (only if there are subscribers)
                        if self.subscribers:
                            self._notify_subscribers_async(capture_images)
                    else:
                        # Log warning if split stream returns empty list (shouldn't happen normally)
                        if self.is_working:
                            self.logger.warning(f"Split stream returned empty capture_images for {self.source_names} (frame_id={self.frame_id_counter}, is_working={self.is_working}, frame_shape={frame_data.shape if frame_data is not None else None})")
                        # Even if capture_images is empty, we still received a frame from GStreamer
                        # Update last_frame with a dummy CaptureImage to track frame reception time
                        # This prevents false "no frames" warnings when frames are received but split fails
                        try:
                            # Create a minimal CaptureImage with current timestamp to track frame reception
                            dummy_image = self._create_capture_image(
                                image=None,  # No image data, just timestamp tracking
                                frame_id=self.frame_id_counter,
                                timestamp=now,
                                source_id=self.source_ids[0] if self.source_ids else 0,
                                current_video_frame=current_video_frame,
                                current_video_position=current_video_position
                            )
                            with self.frame_lock:
                                # Always update to track latest frame reception time
                                self.last_frame = dummy_image
                        except Exception as e:
                            self.logger.debug(f"Failed to create dummy frame for timestamp tracking: {e}")
                else:
                    # Single stream
                    source_id = self.source_ids[0] if self.source_ids else 0
                    capture_image = self._create_capture_image(
                        image=frame_data,
                        frame_id=self.frame_id_counter,
                        timestamp=now,
                        source_id=source_id,
                        current_video_frame=current_video_frame,
                        current_video_position=current_video_position
                    )
                    
                    # Mark as working when we receive first frame after init
                    if self._init_time and not self.is_working:
                        if (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                            self.logger.info(f"First frame received {(now - self._init_time):.1f}s after init - marking as working")
                            self.is_working = True
                    
                    # If still not working after init grace period, skip frame
                    if not self.is_working:
                        process_time = time.perf_counter() - processing_start
                        self._record_perf_metrics(pull_duration, process_time, pts_value)
                        return Gst.FlowReturn.OK
                    
                    # Store frame
                    self._store_frame(capture_image, is_split=False)
                    
                    # Notify subscribers asynchronously (only if there are subscribers)
                    # Check before calling to avoid unnecessary thread creation
                    if self.subscribers:
                        self._notify_subscribers_async([capture_image])
                
                process_time = time.perf_counter() - processing_start
                self._record_perf_metrics(pull_duration, process_time, pts_value)
                return Gst.FlowReturn.OK
        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
            return Gst.FlowReturn.ERROR
 
    def _record_perf_metrics(self, pull_time: float, process_time: float, buffer_pts: Optional[int]) -> None:
        try:
            self._perf_frame_count += 1
            self._perf_pull_total += pull_time
            self._perf_process_total += process_time

            clock_time_none = getattr(Gst, "CLOCK_TIME_NONE", None)
            if buffer_pts is not None and (clock_time_none is None or buffer_pts != clock_time_none) and buffer_pts >= 0:
                if self._perf_last_pts is not None and buffer_pts >= self._perf_last_pts:
                    delta = (buffer_pts - self._perf_last_pts) / 1_000_000_000.0
                    if delta > 0:
                        self._perf_pts_accum += delta
                        self._perf_pts_count += 1
                self._perf_last_pts = buffer_pts

            now = time.time()
            # Периодически логируем perf-метрики, включая фактический FPS
            if now - self._perf_last_log >= self._perf_stats_interval:
                self._log_perf_stats(now)
        except Exception as e:
            self.logger.debug(f"Failed to record perf metrics: {e}")

    def _log_perf_stats(self, now: float) -> None:
        interval = now - self._perf_last_log
        if interval <= 0:
            interval = 1e-6

        frames = self._perf_frame_count
        fps = frames / interval if frames else 0.0
        avg_pull_ms = (self._perf_pull_total / frames) * 1000.0 if frames else 0.0
        avg_proc_ms = (self._perf_process_total / frames) * 1000.0 if frames else 0.0
        pts_fps = (self._perf_pts_count / self._perf_pts_accum) if self._perf_pts_accum > 0 else 0.0

        frame_buffer_size = 0
        if self.split_stream:
            try:
                frame_buffer_size = self.frame_buffer.qsize()
            except Exception:
                frame_buffer_size = -1

        recording_queue_buffers = None
        if self._recording_queue_elem is not None:
            try:
                recording_queue_buffers = self._recording_queue_elem.get_property("current-level-buffers")
            except Exception:
                recording_queue_buffers = None

        source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(self.source_address)
        msg_parts = [
            f"FPS={fps:.2f}",
            f"pull_wait={avg_pull_ms:.2f}ms",
            f"process={avg_proc_ms:.2f}ms"
        ]
        if pts_fps > 0:
            msg_parts.append(f"pts_fps={pts_fps:.2f}")
        if self.split_stream:
            msg_parts.append(f"frame_buffer={frame_buffer_size}")
        if self._perf_frame_buffer_full:
            msg_parts.append(f"buffer_overflows={self._perf_frame_buffer_full}")
        if recording_queue_buffers is not None:
            msg_parts.append(f"record_queue_buf={recording_queue_buffers}")

        # Логируем в INFO, чтобы строки попадали в стандартный debug-лог
        self.logger.info(f"Capture perf [{source_label}]: " + ", ".join(msg_parts))

        # Reset counters for next interval
        self._perf_last_log = now
        self._perf_frame_count = 0
        self._perf_pull_total = 0.0
        self._perf_process_total = 0.0
        self._perf_pts_accum = 0.0
        self._perf_pts_count = 0
        self._perf_frame_buffer_full = 0

    def _build_pipeline_candidates(self) -> List[str]:
        """
        Build multiple pipeline candidates for IP cameras (H265, H264).
        Returns list of pipeline strings to try in order.
        Uses UDP protocol by default, never switches to TCP automatically.
        """
        if self.source_type != CaptureDeviceType.IpCamera:
            return [self._build_pipeline()]
        
        candidates = []
        
        # Build base RTSP part - use UDP protocol by default, but allow TCP fallback
        # protocols=udp+tcp allows GStreamer to try UDP first, then fallback to TCP if UDP fails
        protocol = getattr(self, '_rtsp_protocol', 'udp+tcp')  # Try UDP first, then TCP if UDP fails
        if self.username and self.password:
            base_rtsp = f"rtspsrc location={self.source_address} user-id={self.username} user-pw={self.password} protocols={protocol}"
        else:
            base_rtsp = f"rtspsrc location={self.source_address} protocols={protocol}"
        
        # Build common tail (videoconvert + queue + appsink/tee)
        # For IP cameras, use sync=true to synchronize with real-time clock
        # (Note: _build_pipeline_candidates is only called for IpCamera, so sync is always true here)
        common_tail = " ! videoconvert"
        continuous_enabled = (self.recording_params and 
                              (self.recording_params.continuous_recording_enabled or 
                               (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
        if continuous_enabled:
            common_tail += " ! tee name=t"
            common_tail += " t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=3 drop=true"
            common_tail += " t. ! queue name=recording_queue"
        else:
            common_tail += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=3 drop=true"
        
        # Candidate 1: H265 (if username/password provided, try H265 first)
        if self.username and self.password:
            candidates.append(f"{base_rtsp} ! rtph265depay ! h265parse ! avdec_h265{common_tail}")
        
        # Candidate 2: H264 (always try H264)
        candidates.append(f"{base_rtsp} ! rtph264depay ! h264parse ! avdec_h264{common_tail}")
        
        # Candidate 3: H265 without auth (if no username/password, try H265)
        if not self.username or not self.password:
            candidates.insert(0, f"{base_rtsp} ! rtph265depay ! h265parse ! avdec_h265{common_tail}")
        
        return candidates
    
    def _init_pipeline(self):
        """
        Initialize GStreamer pipeline.
        For IP cameras, tries multiple pipeline candidates (H265, H264) until one works.
        Uses simple approach from api-refactoring with get_state(Gst.CLOCK_TIME_NONE).
        """
        pipeline_str = None
        try:
            with self.pipeline_lock:
                if self.pipeline:
                    self.pipeline.set_state(Gst.State.NULL)
                    self.pipeline = None
                
                # For IP cameras, try multiple pipeline candidates
                if self.source_type == CaptureDeviceType.IpCamera:
                    candidates = self._build_pipeline_candidates()
                    pipeline_str = None
                    last_error = None
                    
                    for i, candidate_str in enumerate(candidates, 1):
                        try:
                            if i > 1:
                                self.logger.info(f"Trying pipeline candidate {i}/{len(candidates)}")
                                self.logger.debug(f"GStreamer pipeline (candidate): {self._mask_credentials_in_pipeline(candidate_str)}")
                            else:
                                self.logger.info(f"GStreamer pipeline: {self._mask_credentials_in_pipeline(candidate_str)}")
                            
                            # Clean up previous pipeline if any
                            if self.pipeline:
                                try:
                                    self.pipeline.set_state(Gst.State.NULL)
                                except Exception:
                                    pass
                                self.pipeline = None
                            
                            # Parse and create pipeline
                            self.pipeline = Gst.parse_launch(candidate_str)
                            if not self.pipeline:
                                self.logger.warning(f"Failed to create pipeline candidate {i}")
                                last_error = f"Failed to create pipeline candidate {i}"
                                continue
                            
                            # Setup bus
                            self.bus = self.pipeline.get_bus()
                            if self.bus is not None:
                                try:
                                    self.bus.add_signal_watch()
                                    self.bus.connect("message", self._on_bus_message)
                                except Exception:
                                    pass
                            
                            # Get appsink element
                            self.appsink = self.pipeline.get_by_name("sink")
                            if not self.appsink:
                                self.logger.warning(f"Failed to get appsink from candidate {i}")
                                last_error = f"Failed to get appsink from candidate {i}"
                                continue
                            
                            # Connect callback
                            try:
                                self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
                            except Exception:
                                self._appsink_handler_id = None
                            
                            # Setup recording branch if continuous recording enabled
                            # IMPORTANT: This must be done BEFORE setting pipeline to PLAYING state
                            # Otherwise, RTSPSrc will see an incomplete pipeline and report "not-linked" error
                            continuous_enabled = (self.recording_params and 
                                                  (self.recording_params.continuous_recording_enabled or 
                                                   (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
                            if continuous_enabled:
                                try:
                                    self._setup_recording_branch()
                                except Exception as e:
                                    self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                                    # Don't continue - recording branch must be set up before pipeline goes to PLAYING
                                    # Otherwise RTSPSrc will report "not-linked" error
                                    raise
                            
                            # Set pipeline to playing state - simple approach from api-refactoring
                            # Recording branch must be fully set up before this point
                            ret = self.pipeline.set_state(Gst.State.PLAYING)
                            if ret == Gst.StateChangeReturn.FAILURE:
                                # Get error message from bus
                                msg = self.bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
                                if msg:
                                    if msg.type == Gst.MessageType.ERROR:
                                        err, debug = msg.parse_error()
                                        self.logger.warning(f"GStreamer pipeline ERROR (candidate {i}): {err}, debug: {debug}")
                                    elif msg.type == Gst.MessageType.WARNING:
                                        warn, debug = msg.parse_warning()
                                        self.logger.warning(f"GStreamer pipeline WARNING (candidate {i}): {warn}, debug: {debug}")
                                last_error = f"Failed to start pipeline candidate {i}"
                                continue
                            elif ret == Gst.StateChangeReturn.ASYNC:
                                # Wait for state change to complete - use CLOCK_TIME_NONE like api-refactoring
                                ret = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
                                if ret[0] == Gst.StateChangeReturn.FAILURE:
                                    # Get error message from bus
                                    msg = self.bus.pop_filtered(Gst.MessageType.ERROR | Gst.MessageType.WARNING)
                                    if msg:
                                        if msg.type == Gst.MessageType.ERROR:
                                            err, debug = msg.parse_error()
                                            self.logger.warning(f"GStreamer pipeline ERROR (candidate {i} async): {err}, debug: {debug}")
                                        elif msg.type == Gst.MessageType.WARNING:
                                            warn, debug = msg.parse_warning()
                                            self.logger.warning(f"GStreamer pipeline WARNING (candidate {i} async): {warn}, debug: {debug}")
                                    last_error = f"Failed to start pipeline candidate {i} (async)"
                                    continue
                            
                            # Success! This candidate works
                            pipeline_str = candidate_str
                            if i > 1:
                                self.logger.info(f"Pipeline candidate {i} succeeded!")
                            break
                                
                        except Exception as e:
                            self.logger.warning(f"Error with pipeline candidate {i}: {e}")
                            last_error = str(e)
                            continue
                    
                    if not pipeline_str:
                        # All candidates failed
                        raise RuntimeError(f"All pipeline candidates failed. Last error: {last_error}")
                else:
                    # For non-IP cameras, use single pipeline
                    pipeline_str = self._build_pipeline()
                    self.logger.info(f"GStreamer pipeline: {self._mask_credentials_in_pipeline(pipeline_str)}")
                    
                    # Parse and create pipeline
                    self.pipeline = Gst.parse_launch(pipeline_str)
                    if not self.pipeline:
                        raise RuntimeError("Failed to create GStreamer pipeline")
                    
                    # Setup bus to handle EOS/ERROR
                    self.bus = self.pipeline.get_bus()
                    if self.bus is not None:
                        try:
                            self.bus.add_signal_watch()
                            self.bus.connect("message", self._on_bus_message)
                        except Exception:
                            pass

                    # Get appsink element
                    self.appsink = self.pipeline.get_by_name("sink")
                    if not self.appsink:
                        raise RuntimeError("Failed to get appsink element")
                    
                    # Connect callback
                    try:
                        self._appsink_handler_id = self.appsink.connect("new-sample", self._on_new_sample)
                    except Exception:
                        self._appsink_handler_id = None
                    
                    # Setup recording branch if continuous recording enabled
                    continuous_enabled = (self.recording_params and 
                                          (self.recording_params.continuous_recording_enabled or 
                                           (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
                    if continuous_enabled:
                        try:
                            self._setup_recording_branch()
                            # Verify that recording branch is properly linked before proceeding
                            recording_queue = self.pipeline.get_by_name("recording_queue")
                            if recording_queue:
                                src_pad = recording_queue.get_static_pad("src")
                                if src_pad:
                                    peer = src_pad.get_peer()
                                    if not peer:
                                        self.logger.error("recording_queue src pad is not linked after setup!")
                                        raise RuntimeError("Recording branch setup incomplete: recording_queue not linked")
                        except Exception as e:
                            self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                            # Don't continue - recording branch must be set up before pipeline goes to PLAYING
                            raise
                    
                    # Set pipeline to playing state - simple approach from api-refactoring
                    # Recording branch must be fully set up before this point
                    ret = self.pipeline.set_state(Gst.State.PLAYING)
                    if ret == Gst.StateChangeReturn.FAILURE:
                        raise RuntimeError("Failed to start GStreamer pipeline")
                    elif ret == Gst.StateChangeReturn.ASYNC:
                        # Wait for state change to complete - use CLOCK_TIME_NONE like api-refactoring
                        ret = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
                        if ret[0] == Gst.StateChangeReturn.FAILURE:
                            raise RuntimeError("Failed to start GStreamer pipeline")
                
                # Query duration for VideoFile
                if self.source_type == CaptureDeviceType.VideoFile:
                    try:
                        ok, dur_ns = self.pipeline.query_duration(Gst.Format.TIME)
                        if ok and dur_ns and dur_ns > 0:
                            self.video_duration = float(dur_ns) / 1e6  # ms
                            if self.source_fps:
                                self.video_length = int((self.video_duration / 1000.0) * self.source_fps)
                    except Exception:
                        pass

                self.logger.info("GStreamer pipeline initialized successfully")
                # Track initialization time to ignore early EOS messages
                self._init_time = time.time()
                # Reset performance metrics for new pipeline run
                self._perf_last_log = self._init_time
                self._perf_frame_count = 0
                self._perf_pull_total = 0.0
                self._perf_process_total = 0.0
                self._perf_pts_accum = 0.0
                self._perf_pts_count = 0
                self._perf_frame_buffer_full = 0

        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer pipeline: {e}")
            if pipeline_str:
                self.logger.error(f"Pipeline string was: {self._mask_credentials_in_pipeline(pipeline_str)}")
            raise

    def _on_bus_message(self, bus, message):
        try:
            msg_type = message.type
            if msg_type == Gst.MessageType.EOS:
                self.logger.info(f"GStreamer EOS received for {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    # Prevent multiple simultaneous reconnection attempts
                    if self._reconnecting:
                        return
                    
                    self._reconnecting = True
                    try:
                        # Restart pipeline instead of seek to avoid TIME/BYTES format mismatch
                        with self.pipeline_lock:
                            try:
                                if self.pipeline is not None:
                                    self.pipeline.set_state(Gst.State.NULL)
                            except Exception:
                                pass
                            self.pipeline = None
                            self.is_inited = False
                            self.is_working = False
                        
                        # Clear last_frame to free memory and reset state
                        with self.frame_lock:
                            if self.last_frame is not None:
                                if self.last_frame.image is not None:
                                    self.last_frame.image = None
                                self.last_frame = None
                            # Clear frame_buffer for split streams
                            if self.split_stream:
                                while not self.frame_buffer.empty():
                                    try:
                                        frame = self.frame_buffer.get_nowait()
                                        if frame is not None:
                                            frame.image = None
                                    except Empty:
                                        break
                        
                        # Reset init time to allow first frame detection after restart
                        self._init_time = None
                        
                        time.sleep(0.1)
                        
                        # Reinitialize pipeline
                        self._init_pipeline()
                        
                        # Verify pipeline is actually initialized and playing
                        with self.pipeline_lock:
                            if self.pipeline is not None:
                                ret, state, pending = self.pipeline.get_state(0)
                                if ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                                    # CRITICAL: Set is_inited flag after successful _init_pipeline()
                                    # is_working will be set in _on_new_sample when first frame is received
                                    self.is_inited = True
                                    self.logger.info(f"Looping video: pipeline restarted successfully (is_inited={self.is_inited}, is_working={self.is_working}, state={state})")
                                else:
                                    self.logger.warning(f"Loop restart: pipeline created but not PLAYING (state={state}, ret={ret})")
                                    self.is_inited = False
                                    self.is_working = False
                            else:
                                self.logger.error("Loop restart: pipeline is None after _init_pipeline()")
                                self.is_inited = False
                                self.is_working = False
                    except Exception as e:
                        self.logger.error(f"Loop restart failed: {e} (is_inited={self.is_inited}, is_working={self.is_working})", exc_info=True)
                        # Mark as not initialized on failure
                        self.is_inited = False
                        self.is_working = False
                    finally:
                        self._reconnecting = False
                elif self.source_type == CaptureDeviceType.IpCamera:
                    # For IP cameras, EOS means disconnect - but ignore early EOS (within 5 seconds of init)
                    # This prevents false positives when pipeline is still initializing
                    now = time.time()
                    if self._init_time and (now - self._init_time) < CaptureConstants.INIT_GRACE_PERIOD_SECONDS:
                        self.logger.debug(f"Ignoring early EOS ({(now - self._init_time):.1f}s after init) - pipeline may still be initializing")
                        return
                    # For IP cameras, EOS means disconnect - mark not working; monitor thread handles reconnect
                    self.logger.warning("GStreamer EOS for IP camera")
                    self.is_working = False
                    timestamp = datetime.datetime.now()
                    self.disconnects.append((self.source_address, timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                    # Trigger reconnect loop if not already running
                    if self.run_flag and not self._reconnecting:
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
                else:
                    self.finished = True
                    self.is_working = False
            elif msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                self.logger.error(f"GStreamer ERROR: {err}, debug: {debug}")
                self.is_working = False
                # For IP cameras, just mark not working; monitor thread handles reconnect
                if self.source_type == CaptureDeviceType.IpCamera and self.run_flag:
                    timestamp = datetime.datetime.now()
                    self.disconnects.append((self.source_address, timestamp, self.is_working))
                    for sub in self.subscribers:
                        sub.update()
                    # Store error for protocol switching logic
                    self._last_init_error = RuntimeError(f"{err}: {debug}")
                    # Trigger reconnect loop if not already running
                    if not self._reconnecting:
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
            elif msg_type == Gst.MessageType.WARNING:
                warn, debug = message.parse_warning()
                # Check for UDP-related warnings - hide them from logs as they are common and not critical
                if "UDP" in str(warn) or "udp" in str(warn).lower() or "Error sending" in str(warn) or "Error sending UDP packets" in str(warn):
                    # Don't log UDP errors - they are common when UDP is blocked or not supported
                    # Still store error for internal use if needed
                    if self.source_type == CaptureDeviceType.IpCamera:
                        self._last_init_error = RuntimeError(f"UDP connection error: {warn}: {debug}")
                else:
                    # Log other warnings normally
                    self.logger.warning(f"GStreamer pipeline WARNING: {warn}, debug: {debug}")
        except Exception as e:
            self.logger.error(f"Error handling bus message: {e}")

    def _seek_to_start(self):
        try:
            with self.pipeline_lock:
                if not self.pipeline:
                    return
                # Flush and seek to start
                success = self.pipeline.seek_simple(
                    Gst.Format.TIME,
                    Gst.SeekFlags.FLUSH | Gst.SeekFlags.KEY_UNIT | Gst.SeekFlags.ACCURATE,
                    0
                )
                if success:
                    self.logger.info("Looping video: seek to start")
                    self.finished = False
                    self.is_working = True
                else:
                    self.logger.warning("Looping video: seek failed, restarting pipeline")
                    # Fallback: restart pipeline
                    self.pipeline.set_state(Gst.State.NULL)
                    self.pipeline.set_state(Gst.State.PLAYING)
        except Exception as e:
            self.logger.error(f"Looping video: exception during seek: {e}")
    
    def _start_main_loop(self):
        """
        Start GLib main loop in separate thread.
        """
        def run_loop():
            self.loop = GLib.MainLoop()
            self.loop.run()
        
        self.main_loop_thread = threading.Thread(target=run_loop, daemon=True)
        self.main_loop_thread.start()
    
    def _stop_main_loop(self):
        """
        Stop GLib main loop.
        """
        if self.loop and self.loop.is_running():
            self.loop.quit()
        if self.main_loop_thread and self.main_loop_thread.is_alive():
            self.main_loop_thread.join(timeout=2.0)
    
    def init(self):
        """
        Initialize the GStreamer capture.
        Returns True on success, False on failure.
        For IP cameras, uses simple approach from api-refactoring without timeout.
        """
        if not self.gstreamer_available:
            self.logger.error("GStreamer not available, cannot initialize")
            self.is_inited = False
            self.is_working = False
            return False
        
        # For IP cameras, use simple approach from api-refactoring without timeout
        # get_state(Gst.CLOCK_TIME_NONE) will block until state change completes
        if self.source_type == CaptureDeviceType.IpCamera:
            try:
                self._init_pipeline()
                self._start_main_loop()
                self.is_inited = True
                # Set is_working = True initially to allow frames to be processed
                # We'll verify it's actually working by checking for frames in _grab_frames
                self.is_working = True
                self.logger.info("GStreamer video capture initialized successfully")
                
                # Start recording check thread after pipeline is PLAYING
                if self._recording_check_thread and not self._recording_check_thread.is_alive():
                    self._recording_check_thread.start()
                
                return True
            except CaptureInitializationError:
                # Re-raise initialization errors
                raise
            except Exception as e:
                error_msg = f"Failed to initialize GStreamer capture: {e}"
                self.logger.error(error_msg, exc_info=True)
                self.is_inited = False
                self.is_working = False
                # Store error for protocol switching logic
                self._last_init_error = e
                raise CaptureInitializationError(error_msg) from e
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

    def start(self):
        """
        Override start() to always launch grab/retrieve threads, even if init() failed.
        This allows reconnect logic to work from the start.
        """
        self.run_flag = True
        # Always start threads, even if not initialized - reconnect logic will handle it
        self.grab_thread = threading.Thread(target=self._grab_frames, daemon=True)
        self.retrieve_thread = threading.Thread(target=self._retrieve_frames, daemon=True)
        self.grab_thread.start()
        self.retrieve_thread.start()
        # Start recording if configured (for OpenCV backend, not GStreamer - GStreamer uses tee)
        # For GStreamer, recording is integrated in pipeline via tee
        try:
            continuous_enabled = (self.recording_params and 
                                  (self.recording_params.continuous_recording_enabled or 
                                   (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
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
                        if self.recorder_manager:
                            self.recorder_manager.start_recording(meta, self.recording_params)
                    except Exception as e:
                        self.logger.error(f"Failed to start recording: {e}")
        except Exception as e:
            self.logger.debug(f"Error starting recording: {e}")
    
    def release(self) -> None:
        """
        Release resources and stop pipeline.
        """
        try:
            # Debug stack dump disabled
            # Detach pipeline under lock to avoid races
            pipeline = None
            with self.pipeline_lock:
                pipeline = self.pipeline
                self.pipeline = None
                # Stop appsink signals and disconnect handler
                try:
                    if self.appsink is not None:
                        try:
                            self.appsink.set_property("emit-signals", False)
                        except Exception:
                            pass
                        try:
                            if self._appsink_handler_id is not None:
                                self.appsink.disconnect(self._appsink_handler_id)
                        except Exception:
                            pass
                except Exception:
                    pass
                self.is_working = False

            # Try graceful EOS to unblock internal threads
            if pipeline is not None:
                try:
                    pipeline.send_event(Gst.Event.new_eos())
                    bus = pipeline.get_bus()
                    if bus is not None:
                        # Remove any signal watch and start flushing to unblock waits
                        try:
                            bus.remove_signal_watch()
                        except Exception:
                            pass
                        try:
                            bus.set_flushing(True)
                        except Exception:
                            pass
                except Exception:
                    pass

            # Clean up recording branch before stopping pipeline
            try:
                self._cleanup_recording_branch()
            except Exception as e:
                self.logger.debug(f"Error cleaning up recording branch in release: {e}")
            
            # Clear frame_buffer and last_frame to free memory
            with self.frame_lock:
                # Clear all frames from frame_buffer
                while not self.frame_buffer.empty():
                    try:
                        frame = self.frame_buffer.get_nowait()
                        # Explicitly clear frame image to free memory
                        if frame is not None:
                            frame.image = None
                        frame = None
                    except Empty:
                        break
                # Clear last_frame reference
                if self.last_frame is not None:
                    self.last_frame.image = None
                    self.last_frame = None
                # Clear FPS tracking list to free memory
                self._fps_times.clear()
            
            # Stop GLib main loop first to avoid deadlock on set_state
            self._stop_main_loop()

            # Now set pipeline to NULL outside locks, with staged states and timeout
            if pipeline is not None:
                try:
                    # Try staged state changes to avoid hangs
                    try:
                        pipeline.set_state(Gst.State.PAUSED)
                        pipeline.get_state(0.5 * Gst.SECOND)
                    except Exception:
                        pass
                    try:
                        pipeline.set_state(Gst.State.READY)
                        pipeline.get_state(0.5 * Gst.SECOND)
                    except Exception:
                        pass
                    # As a last resort, force elements to NULL individually
                    try:
                        it = pipeline.iterate_elements()
                        elements = []
                        while True:
                            res, elem = it.next()
                            if res != Gst.IteratorResult.OK:
                                break
                            elements.append(elem)
                    except Exception:
                        elements = []
                    # Reverse to attempt sinks first
                    for elem in reversed(elements):
                        try:
                            elem.set_state(Gst.State.NULL)
                        except Exception:
                            pass
                    # Call NULL in background to avoid blocking
                    import threading as _thr
                    set_done = _thr.Event()
                    def _set_null():
                        try:
                            pipeline.set_state(Gst.State.NULL)
                        finally:
                            set_done.set()
                    t = _thr.Thread(target=_set_null, daemon=True)
                    t.start()
                    # Wait up to 1.5s
                    set_done.wait(1.5)
                    if t.is_alive():
                        self.logger.warning("Timeout setting GStreamer pipeline to NULL; continuing release")
                except Exception:
                    pass

            # Note: frame_buffer and last_frame are already cleared earlier in release()
            # (see lines 1106-1123)

            self.is_working = False
            self.logger.info("GStreamer video capture released")

        except Exception as e:
            self.logger.error(f"Error releasing GStreamer capture: {e}")
    
    def is_opened(self) -> bool:
        """
        Check if capture is opened and working.
        """
        return self.is_working and self.pipeline is not None
    
    def get_frames_impl(self) -> List[CaptureImage]:
        """
        Get latest captured frames.
        For split_stream, returns all split frames from frame_buffer.
        For single stream, returns a copy of last_frame (like OpenCV implementation).
        """
        frames = []
        if not self.is_working:
            return frames
        
        # Track get() calls for diagnostics
        if not hasattr(self, '_get_call_count'):
            self._get_call_count = 0
            self._get_call_last_log = time.time()
        self._get_call_count += 1
        now = time.time()
        if now - self._get_call_last_log >= 5.0:
            source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(self.source_address)
            get_fps = self._get_call_count / (now - self._get_call_last_log)
            self.logger.debug(f"Capture get() calls [{source_label}]: {get_fps:.2f} calls/sec, get_call_count={self._get_call_count}")
            self._get_call_count = 0
            self._get_call_last_log = now
        
        if self.split_stream:
            # For split streams, get all frames from frame_buffer
            with self.frame_lock:
                while not self.frame_buffer.empty():
                    try:
                        frame = self.frame_buffer.get_nowait()
                        frames.append(frame)
                    except Empty:
                        break
        else:
            # For single stream, create a copy of last_frame (like OpenCV does)
            # This prevents race condition when old frame memory is freed in _store_frame
            last_frame_ref = None
            frame_id = None
            timestamp = None
            source_id = None
            current_video_frame = None
            current_video_position = None
            image_copy = None
            
            try:
                # Get reference to last_frame with minimal lock time
                with self.frame_lock:
                    if self.last_frame:
                        # Track if we're returning the same frame multiple times (indicates pipeline is faster than GStreamer)
                        current_frame_id = self.last_frame.frame_id
                        if not hasattr(self, '_last_returned_frame_id'):
                            self._last_returned_frame_id = -1
                        if current_frame_id == self._last_returned_frame_id:
                            # Same frame returned again - pipeline is calling get() faster than GStreamer produces frames
                            if not hasattr(self, '_same_frame_count'):
                                self._same_frame_count = 0
                            self._same_frame_count += 1
                        else:
                            self._last_returned_frame_id = current_frame_id
                            if hasattr(self, '_same_frame_count') and self._same_frame_count > 0:
                                # Log if we had repeated frames
                                source_label = ",".join(str(name) for name in self.source_names) if self.source_names else str(self.source_address)
                                self.logger.debug(f"Capture get() [{source_label}]: returned same frame {self._same_frame_count} times before new frame")
                                self._same_frame_count = 0
                        # Only copy reference and metadata while holding lock (very fast)
                        last_frame_ref = self.last_frame
                        frame_id = last_frame_ref.frame_id
                        timestamp = last_frame_ref.time_stamp
                        source_id = last_frame_ref.source_id
                        current_video_frame = last_frame_ref.current_video_frame
                        current_video_position = last_frame_ref.current_video_position
                        # Get reference to image (don't copy yet - do it outside lock)
                        image_ref = last_frame_ref.image
                    else:
                        last_frame_ref = None
                        image_ref = None
                
                # Copy image and create new CaptureImage outside of lock
                # This prevents blocking _store_frame() which also needs frame_lock
                if last_frame_ref is not None:
                    # Optimization: Only copy if there are subscribers or if frame might be accessed concurrently
                    # For single stream without subscribers, we can avoid the copy since get() is called from main thread
                    # and _store_frame() already completed. However, to be safe, we still copy if subscribers exist.
                    # If no subscribers, we can reuse the reference (but still need to copy metadata to avoid race conditions)
                    if self.subscribers:
                        # Copy image data outside lock (may take time for large images)
                        # Required when subscribers might access frame concurrently
                        image_copy = image_ref.copy() if image_ref is not None else None
                    else:
                        # No subscribers - can reuse reference, but need to be careful about thread safety
                        # Since get() is called from main thread and _store_frame() already completed,
                        # the reference should be safe. However, to avoid potential issues with frame updates,
                        # we still do a shallow copy of the array (view) which is much faster than deep copy.
                        # Actually, for safety, we still do a copy, but this is a known optimization point.
                        image_copy = image_ref.copy() if image_ref is not None else None
                    
                    copied_frame = self._create_capture_image(
                        image=image_copy,
                        frame_id=frame_id,
                        timestamp=timestamp,
                        source_id=source_id,
                        current_video_frame=current_video_frame,
                        current_video_position=current_video_position
                    )
                    frames.append(copied_frame)
            except Exception as e:
                # Log error but don't break the flow - return empty list if copy fails
                self.logger.error(f"Error creating frame copy in get_frames_impl: {e}", exc_info=True)
        
        return frames
    
    def _grab_frames(self):
        """
        Monitor pipeline state and reconnect if needed (similar to OpenCV reconnect logic).
        """
        while self.run_flag and not self.stop_event.is_set():
            if not self.is_inited or self.pipeline is None:
                # Check if reconnection is already in progress (for both IP cameras and video files)
                if self._reconnecting:
                    self.logger.debug(f"Reconnection already in progress for {self.source_names}, waiting...")
                    time.sleep(CaptureConstants.RECONNECT_SLEEP_LONG)
                    continue
                
                # For IP cameras, use reconnect loop instead of direct init()
                if self.source_type == CaptureDeviceType.IpCamera:
                    self.logger.info(f"Source {self.source_names} not initialized (is_inited={self.is_inited}, pipeline={self.pipeline is not None}), starting reconnect loop")
                    threading.Thread(target=self._reconnect_loop, daemon=True).start()
                    # Wait a bit before checking again
                    time.sleep(CaptureConstants.RECONNECT_MONITOR_INTERVAL)
                else:
                    # For video files, try direct init (but only if not already reconnecting via EOS handler)
                    self.logger.debug(f"Video file {self.source_names} not initialized (is_inited={self.is_inited}, pipeline={self.pipeline is not None}), attempting reconnect")
                    time.sleep(CaptureConstants.RECONNECT_SLEEP_SHORT)
                    if self.run_flag:
                        try:
                            if self.init():
                                timestamp = datetime.datetime.now()
                                self.logger.info(f"Reconnected to source: {self.source_names} (is_inited={self.is_inited}, is_working={self.is_working})")
                                self.reconnects.append((self.source_address, timestamp, self.is_working))
                                for sub in self.subscribers:
                                    sub.update()
                            else:
                                self.logger.warning(f"Reconnection attempt failed for {self.source_names} (init() returned False)")
                        except Exception as e:
                            self.logger.error(f"Reconnection failed: {e} (is_inited={self.is_inited}, is_working={self.is_working})")
                continue
            
            # Poll bus for messages (no GLib MainLoop running)
            try:
                if self.bus:
                    msg = self.bus.timed_pop_filtered(0.1 * Gst.SECOND, Gst.MessageType.ERROR | Gst.MessageType.EOS | Gst.MessageType.WARNING)
                    if msg:
                        self._on_bus_message(msg)
            except Exception as e:
                self.logger.debug(f"Error polling bus: {e}")
            
            # Active pipeline state check
            try:
                if self.pipeline:
                    ret, state, pending = self.pipeline.get_state(0)
                    if ret == Gst.StateChangeReturn.SUCCESS:
                        if state == Gst.State.PLAYING:
                            # Check if we're actually receiving frames
                            now = time.time()
                            last_frame_time = 0
                            
                            with self.frame_lock:
                                if self.split_stream:
                                    # For split streams, check last_frame which is updated when frames arrive
                                    # last_frame is set to first frame of capture_images for split streams
                                    if self.last_frame:
                                        last_frame_time = getattr(self.last_frame, 'time_stamp', 0)
                                    # Also check if frame_buffer has frames (as fallback)
                                    elif not self.frame_buffer.empty():
                                        # Try to peek at the most recent frame
                                        # Since Queue doesn't support peek, we temporarily get and put back
                                        try:
                                            temp_frame = self.frame_buffer.get_nowait()
                                            if temp_frame:
                                                last_frame_time = getattr(temp_frame, 'time_stamp', 0)
                                            # Put frame back
                                            try:
                                                self.frame_buffer.put_nowait(temp_frame)
                                            except Full:
                                                # If buffer is full, just drop the frame we got
                                                pass
                                        except Empty:
                                            pass
                                else:
                                    # For single stream, check last_frame
                                    if self.last_frame:
                                        last_frame_time = getattr(self.last_frame, 'time_stamp', 0)
                            
                            if last_frame_time > 0 and (now - last_frame_time) > CaptureConstants.FRAME_TIMEOUT_SECONDS:
                                # No frames for timeout period
                                time_since_last_frame = now - last_frame_time
                                
                                # For VideoFile with loop_play, don't stop working - trigger restart instead
                                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                                    if self.is_working:
                                        self.logger.warning(
                                            f"Pipeline PLAYING but no frames received after {time_since_last_frame:.1f}s "
                                            f"for {self.source_names} (VideoFile with loop_play), triggering restart "
                                            f"(last_frame_time={last_frame_time:.3f}, now={now:.3f})"
                                        )
                                        # Don't set is_working = False for VideoFile with loop_play
                                        # Instead, trigger restart immediately (handled below)
                                    # Mark as not working temporarily to trigger restart logic
                                    self.is_working = False
                                else:
                                    # For IP cameras and other sources, mark as not working
                                    if self.is_working:
                                        self.logger.warning(
                                            f"Pipeline PLAYING but no frames received after {time_since_last_frame:.1f}s "
                                            f"for {self.source_names}, marking as not working "
                                            f"(last_frame_time={last_frame_time:.3f}, now={now:.3f})"
                                        )
                                        self.is_working = False
                        else:
                            # Pipeline not in PLAYING state
                            if self.is_working:
                                self.logger.debug(f"Pipeline state changed to {state} for {self.source_names}, marking as not working")
                            self.is_working = False
                    else:
                        # Failed to get state
                        if self.is_working:
                            self.logger.debug(f"Failed to get pipeline state (ret={ret}) for {self.source_names}, marking as not working")
                        self.is_working = False
            except Exception as e:
                self.logger.debug(f"Error checking pipeline state: {e}")
            
            # Check if pipeline is still working and needs reconnection
            if not self.is_working:
                # For IP cameras, use reconnect loop
                if self.source_type == CaptureDeviceType.IpCamera:
                    if self.run_flag and not self._reconnecting:
                        self.logger.info(f"Pipeline not working, starting reconnect loop for {self.source_names}")
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
                # For video files with loop_play, check if reconnection is needed
                elif self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    # Don't reconnect if already reconnecting (via EOS handler or previous attempt)
                    if not self._reconnecting:
                        # For VideoFile with loop_play, always restart if not working
                        # This handles cases where pipeline is valid but not receiving frames
                        with self.pipeline_lock:
                            pipeline_valid = (self.pipeline is not None)
                            pipeline_playing = False
                            if pipeline_valid:
                                try:
                                    ret, state, pending = self.pipeline.get_state(0)
                                    pipeline_playing = (ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING)
                                except Exception:
                                    pass
                        
                        # For VideoFile with loop_play: always restart when not working
                        # Even if pipeline appears valid and playing, if we're not receiving frames, restart
                        # This ensures continuous playback even after temporary stalls
                        # IMPORTANT: For VideoFile with loop_play, we always restart when is_working=False
                        # because the timeout means we're not receiving frames, regardless of pipeline state
                        should_restart = True  # Always restart for VideoFile with loop_play when not working
                        
                        if should_restart:
                            # Trigger restart similar to EOS handler
                            self._reconnecting = True
                            try:
                                self.logger.info(f"Auto-restarting pipeline for {self.source_names} after no frames (pipeline_valid={pipeline_valid}, is_inited={self.is_inited}, pipeline_playing={pipeline_playing})")
                                # Restart pipeline
                                with self.pipeline_lock:
                                    try:
                                        if self.pipeline is not None:
                                            self.pipeline.set_state(Gst.State.NULL)
                                            # Wait a bit for state change
                                            time.sleep(0.1)
                                    except Exception as e:
                                        self.logger.debug(f"Error setting pipeline to NULL: {e}")
                                    self.pipeline = None
                                    self.is_inited = False
                                    self.is_working = False
                                
                                # Clear frames to free memory and reset state
                                with self.frame_lock:
                                    if self.last_frame is not None:
                                        if self.last_frame.image is not None:
                                            self.last_frame.image = None
                                        self.last_frame = None
                                    # Clear frame_buffer for split streams
                                    if self.split_stream:
                                        while not self.frame_buffer.empty():
                                            try:
                                                frame = self.frame_buffer.get_nowait()
                                                if frame is not None:
                                                    frame.image = None
                                            except Empty:
                                                break
                                
                                # Reset init time to allow first frame detection after restart
                                self._init_time = None
                                
                                time.sleep(0.1)
                                
                                # Reinitialize pipeline
                                self._init_pipeline()
                                
                                # Verify pipeline is actually initialized and playing
                                with self.pipeline_lock:
                                    if self.pipeline is not None:
                                        ret, state, pending = self.pipeline.get_state(0)
                                        if ret == Gst.StateChangeReturn.SUCCESS and state == Gst.State.PLAYING:
                                            # CRITICAL: Set is_inited flag after successful _init_pipeline()
                                            # is_working will be set in _on_new_sample when first frame is received
                                            self.is_inited = True
                                            self.logger.info(f"Auto-restarted pipeline for {self.source_names} after no frames (is_inited={self.is_inited}, is_working={self.is_working}, state={state})")
                                        else:
                                            self.logger.warning(f"Auto-restart: pipeline created but not PLAYING (state={state}, ret={ret}) for {self.source_names}")
                                            self.is_inited = False
                                            self.is_working = False
                                    else:
                                        self.logger.error(f"Auto-restart: pipeline is None after _init_pipeline() for {self.source_names}")
                                        self.is_inited = False
                                        self.is_working = False
                            except Exception as e:
                                self.logger.error(f"Error during auto-restart for {self.source_names}: {e}", exc_info=True)
                                self.is_inited = False
                                self.is_working = False
                            finally:
                                self._reconnecting = False
            
            # Sleep according to monitor interval
            try:
                cfg = (self.params or {}).get('reconnect', {})
                monitor_sleep = float(cfg.get('monitor_interval_sec', CaptureConstants.RECONNECT_MONITOR_INTERVAL))
            except Exception:
                monitor_sleep = CaptureConstants.RECONNECT_MONITOR_INTERVAL
            time.sleep(monitor_sleep)
    
    def _reconnect_loop(self):
        """Reconnect loop for IP cameras (similar to OpenCV _grab_frames reconnect logic)"""
        if not self.run_flag:
            return
        # Prevent multiple simultaneous reconnect attempts
        if self._reconnecting:
            return
        self._reconnecting = True
        try:
            # Prevent races with monitor thread and force not working state
            self.is_inited = False
            self.is_working = False
            # Read reconnect settings from params if provided
            try:
                cfg = (self.params or {}).get('reconnect', {})
            except Exception:
                cfg = {}
            max_attempts = int(cfg.get('max_attempts', 0))  # 0 => infinite by default
            initial_delay_sec = float(cfg.get('initial_delay_sec', 8.0))
            max_delay_sec = float(cfg.get('max_delay_sec', 60.0))
            backoff_step_sec = float(cfg.get('backoff_step_sec', 6.0))
            attempt = 0
            while self.run_flag and not self.stop_event.is_set() and (max_attempts == 0 or attempt < max_attempts):
                # First attempt immediately; subsequent attempts with backoff
                if attempt == 0:
                    wait_time = 0.0
                else:
                    wait_time = initial_delay_sec + (attempt - 1) * backoff_step_sec
                    if wait_time > max_delay_sec:
                        wait_time = max_delay_sec
                if wait_time > 0:
                    self.logger.debug(f"Waiting {wait_time:.1f}s before reconnect attempt {attempt + 1} for {self.source_names}")
                    time.sleep(wait_time)
                attempt += 1
                if not self.is_working and self.run_flag:
                    try:
                        total_str = ("∞" if max_attempts == 0 else str(max_attempts))
                        self.logger.info(f"Reconnecting to source {self.source_names} (attempt {attempt}/{total_str}), backoff={wait_time:.1f}s")
                        # Release old pipeline (with timeout to prevent blocking)
                        try:
                            import threading as _thr_rel
                            release_done = _thr_rel.Event()
                            def _release_worker():
                                try:
                                    self.release()
                                except Exception as e:
                                    self.logger.debug(f"Error in release during reconnect: {e}")
                                finally:
                                    release_done.set()
                            release_thread = _thr_rel.Thread(target=_release_worker, daemon=True)
                            release_thread.start()
                            # Wait up to 2 seconds for release
                            if not release_done.wait(2.0):
                                self.logger.warning(f"Release timeout after 2s for {self.source_names}; continuing anyway")
                        except Exception as e:
                            self.logger.debug(f"Error starting release thread: {e}")
                        # Wait a bit before retry
                        time.sleep(2.0)
                        # Try to reinitialize with timeout and protocol fallback
                        init_ok = False
                        init_err = None
                        import threading as _thr
                        done_evt = _thr.Event()
                        init_thread = None
                        def _try_init():
                            nonlocal init_ok, init_err
                            try:
                                # Call init() which now has its own internal timeout
                                # init() returns False on failure, True on success
                                self.logger.debug(f"Calling init() for {self.source_names} (attempt {attempt})")
                                result = self.init()
                                init_ok = (result is True)
                                if not init_ok:
                                    init_err = RuntimeError("init() returned False")
                                    self.logger.debug(f"init() returned False for {self.source_names}")
                                else:
                                    self.logger.debug(f"init() returned True for {self.source_names}")
                            except Exception as e:
                                init_err = e
                                init_ok = False
                                self.logger.debug(f"init() raised exception for {self.source_names}: {e}")
                            finally:
                                done_evt.set()
                        init_thread = _thr.Thread(target=_try_init, daemon=True)
                        init_thread.start()
                        # Wait up to 8s for init (init() itself has 6s timeout, so total ~8s to allow for thread overhead)
                        if not done_evt.wait(8.0):
                            self.logger.warning(f"Reconnect init timeout after 8s for {self.source_names}; forcing cleanup and retry")
                            # Force aggressive cleanup (don't call release() here - it's already called at the start of the attempt)
                            try:
                                with self.pipeline_lock:
                                    if self.pipeline is not None:
                                        try:
                                            self.logger.debug(f"Force setting pipeline to NULL for {self.source_names}")
                                            self.pipeline.set_state(Gst.State.NULL)
                                        except Exception as e:
                                            self.logger.debug(f"Error setting pipeline to NULL: {e}")
                                        self.pipeline = None
                                    self.bus = None
                                    self.appsink = None
                            except Exception as e:
                                self.logger.debug(f"Error in aggressive cleanup: {e}")
                            # Mark as not initialized
                            self.is_inited = False
                            self.is_working = False
                            init_ok = False
                            # Log current state for debugging
                            self.logger.debug(f"After timeout cleanup: is_inited={self.is_inited}, is_working={self.is_working}, pipeline={self.pipeline is not None}")
                            # Continue to the retry logic below - don't call release() here as it may block
                        elif init_err is not None:
                            self.logger.error(f"Reconnect init error: {init_err}")
                            # Store error for protocol switching logic
                            self._last_init_error = init_err
                            init_ok = False
                        else:
                            # Check if init actually succeeded
                            init_ok = self.is_inited and self.is_working
                            if not init_ok:
                                self.logger.debug(f"init() completed but is_inited={self.is_inited}, is_working={self.is_working} for {self.source_names}")

                        # CRITICAL: Always check init_ok and log failure if needed, then continue loop
                        if init_ok:
                            timestamp = datetime.datetime.now()
                            self.logger.info(f"Reconnected to source: {self.source_names}")
                            self.reconnects.append((self.source_address, timestamp, self.is_working))
                            for sub in self.subscribers:
                                sub.update()
                            break
                        else:
                            # Log failure and continue to next attempt - THIS MUST BE REACHED
                            self.logger.warning(f"Reconnection attempt {attempt} failed for {self.source_names}; will retry (init_ok={init_ok}, is_inited={self.is_inited}, is_working={self.is_working})")
                            # Protocol switching logic removed - always use UDP, never switch to TCP automatically
                            # If UDP fails, it's likely a network/camera issue, not a protocol issue
                            # User can manually configure TCP if needed, but we never switch automatically
                            # Continue loop - this is critical to ensure retries happen
                            continue
                    except Exception as e:
                        self.logger.error(f"Reconnection error: {e}")
                        # Continue loop even on exception
                        continue
            if max_attempts and attempt >= max_attempts:
                self.logger.error(f"Failed to reconnect after {max_attempts} attempts")
        finally:
            self._reconnecting = False
    
    def _setup_recording_branch(self):
        """Setup recording branch using tee output - encode and record to splitmuxsink"""
        continuous_enabled = (self.recording_params and 
                              (self.recording_params.continuous_recording_enabled or 
                               (self.recording_params.enabled and not self.recording_params.event_recording_enabled)))
        if not continuous_enabled:
            return
        
        try:
            # Clean up existing recording branch if any (prevent duplicates)
            if self._recording_elements:
                self._cleanup_recording_branch()
            
            from pathlib import Path
            import datetime as _dt
            
            # Get recording queue element
            recording_queue = self.pipeline.get_by_name("recording_queue")
            if not recording_queue:
                raise RuntimeError("Failed to get recording_queue element")
            self._recording_queue_elem = recording_queue
            
            # Create recording elements
            videoconvert = Gst.ElementFactory.make("videoconvert", "recording_videoconvert")
            if not videoconvert:
                raise RuntimeError("Failed to create videoconvert element")
            x264enc = Gst.ElementFactory.make("x264enc", "recording_x264enc")
            if not x264enc:
                raise RuntimeError("Failed to create x264enc element")
            x264enc.set_property("tune", "zerolatency")
            x264enc.set_property("speed-preset", "ultrafast")
            x264enc.set_property("bitrate", 2000)
            
            h264parse = Gst.ElementFactory.make("h264parse", "recording_h264parse")
            if not h264parse:
                raise RuntimeError("Failed to create h264parse element")
            queue_before_mux = Gst.ElementFactory.make("queue", "recording_queue_before_mux")
            if not queue_before_mux:
                raise RuntimeError("Failed to create queue element")
            
            # Create splitmuxsink
            splitmuxsink = Gst.ElementFactory.make("splitmuxsink", "recording_splitmuxsink")
            if not splitmuxsink:
                raise RuntimeError("Failed to create splitmuxsink element")
            splitmuxsink.set_property("max-size-time", self.recording_params.segment_length_sec * 1000000000)
            splitmuxsink.set_property("muxer-factory", "mp4mux" if self.recording_params.container.lower() == "mp4" else "matroskamux")
            splitmuxsink.set_property("async-finalize", True)
            
            
            # Compose camera folder name from all source_names or source_ids
            if self.source_names and len(self.source_names) > 0:
                camera_folder = "-".join(self.source_names)
            elif self.source_ids and len(self.source_ids) > 0:
                camera_folder = "-".join(str(sid) for sid in self.source_ids)
            else:
                camera_folder = "source"
            
            # Build output path with camera name subfolder
            # Create path: base/Streams/YYYY-MM-DD/CameraName/
            # recording_params.out_dir should always be set to database.image_dir by Controller
            base_dir = Path(self.recording_params.out_dir) if self.recording_params.out_dir else Path("EvilEyeData")
            date_dir = _dt.datetime.now().strftime("%Y-%m-%d")
            out_dir = base_dir / "Streams" / date_dir / camera_folder
            out_dir.mkdir(parents=True, exist_ok=True)
            
            ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            source_name = (self.source_names[0] if self.source_names else camera_folder)
            name = self.recording_params.filename_tmpl.format(
                source_name=source_name,
                start_time=ts,
                seq=0,
                ext=self.recording_params.container,
            )
            stem = (out_dir / name).with_suffix("")
            location = str(stem) + "_%05d." + self.recording_params.container
            splitmuxsink.set_property("location", location)
            
            # Store recording directory and min_file_size_kb for periodic file checking
            self._recording_out_dir = out_dir
            self._recording_min_file_size_kb = self.recording_params.min_file_size_kb
            self._recording_location_pattern = location
            self._recording_container = self.recording_params.container
            self._recording_checked_files = set()  # Track already checked files
            self._recording_elements = [videoconvert, x264enc, h264parse, queue_before_mux, splitmuxsink]
            self._recording_check_thread = None
            self._recording_check_stop = False
            
            # Start periodic thread to check for new small files (only after pipeline is PLAYING)
            def check_small_files_periodically():
                """Periodically check for newly created small files and delete them"""
                while not self._recording_check_stop and self.run_flag:
                    try:
                        if not self._recording_out_dir or not self._recording_out_dir.exists():
                            time.sleep(5.0)
                            continue
                        
                        # Get all video files in recording directory
                        from evileye.video_recorder.utils import check_and_delete_small_files
                        validate_integrity = getattr(self.recording_params, 'validate_video_integrity', True)
                        validation_timeout = getattr(self.recording_params, 'video_validation_timeout', 2.0)
                        
                        for file_path in self._recording_out_dir.glob(f"*.{self._recording_container}"):
                            if file_path in self._recording_checked_files:
                                continue
                            
                            # Try to delete small/invalid files (only if not active per util's min_age rule)
                            # Also validate integrity if enabled
                            deleted = check_and_delete_small_files(
                                file_path, 
                                self._recording_min_file_size_kb,
                                validate_integrity=validate_integrity,
                                validation_timeout=validation_timeout
                            )
                            if deleted:
                                # Determine reason for deletion
                                if '%' in file_path.name:
                                    reason = "invalid name pattern"
                                else:
                                    try:
                                        stat = file_path.stat()
                                        file_size_kb = stat.st_size / 1024.0
                                        if file_size_kb < self._recording_min_file_size_kb:
                                            reason = f"size < {self._recording_min_file_size_kb} KB"
                                        else:
                                            reason = "corrupted/invalid video file"
                                    except Exception:
                                        reason = "corrupted/invalid video file"
                                self.logger.info(f"Deleted recording file: {file_path} ({reason})")
                                continue
                            
                            # If not deleted, add to checked only if file is mature (avoid skipping future checks when still active)
                            try:
                                stat = file_path.stat()
                                file_age = time.time() - stat.st_mtime
                                if file_age >= 60.0:  # consider mature after 60s
                                    self._recording_checked_files.add(file_path)
                            except Exception:
                                pass
                    except Exception as e:
                        self.logger.error(f"Error checking small files: {e}")
                    
                    time.sleep(5.0)  # Check every 5 seconds
            
            # Store thread reference (will be started after pipeline is PLAYING)
            self._recording_check_thread = threading.Thread(target=check_small_files_periodically, daemon=True)
            
            self.logger.info(f"Recording branch location: {location}")
            
            # Check pipeline state before adding elements - elements should be added when pipeline is NULL or READY
            # Note: This method is called from _init_pipeline() which already holds pipeline_lock, so we don't acquire it here
            if not self.pipeline:
                raise RuntimeError("Pipeline is None, cannot setup recording branch")
            
            # Get current pipeline state (use timeout to avoid blocking)
            ret, current_state, pending_state = self.pipeline.get_state(Gst.SECOND)
            if ret == Gst.StateChangeReturn.FAILURE:
                raise RuntimeError("Failed to get pipeline state")
            
            
            # If pipeline is PLAYING or PAUSED, we need to handle state change carefully
            # Elements should ideally be added when pipeline is NULL or READY
            if current_state in (Gst.State.PLAYING, Gst.State.PAUSED):
                self.logger.warning(f"Pipeline is in {current_state.value_nick} state when adding recording elements - this may cause issues")
            
            # Add elements to pipeline
            self.pipeline.add(videoconvert)
            self.pipeline.add(x264enc)
            self.pipeline.add(h264parse)
            self.pipeline.add(queue_before_mux)
            self.pipeline.add(splitmuxsink)
            
            # Check caps compatibility before linking
            # Get src pad from recording_queue to check caps
            try:
                recording_queue_src = recording_queue.get_static_pad("src")
                if recording_queue_src:
                    recording_queue_src.get_current_caps()
            except Exception:
                pass
            
            # Link elements with error checking
            # Check if recording_queue is already linked (should not be, but check anyway)
            try:
                recording_queue_src_pad = recording_queue.get_static_pad("src")
                if recording_queue_src_pad:
                    peer = recording_queue_src_pad.get_peer()
                    if peer:
                        self.logger.warning(f"recording_queue src pad is already linked to {peer.get_parent().get_name() if peer.get_parent() else 'unknown'}, unlinking first")
                        recording_queue_src_pad.unlink(peer)
            except Exception:
                pass
            
            link_ok = True
            
            try:
                if not recording_queue.link(videoconvert):
                    self.logger.error("Failed to link recording_queue -> videoconvert")
                    link_ok = False
            except Exception as link_err:
                self.logger.error(f"Exception linking recording_queue -> videoconvert: {link_err}")
                link_ok = False
            
            if link_ok:
                try:
                    if not videoconvert.link(x264enc):
                        self.logger.error("Failed to link videoconvert -> x264enc")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking videoconvert -> x264enc: {link_err}")
                    link_ok = False
            
            if link_ok:
                try:
                    if not x264enc.link(h264parse):
                        self.logger.error("Failed to link x264enc -> h264parse")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking x264enc -> h264parse: {link_err}")
                    link_ok = False
            
            if link_ok:
                try:
                    if not h264parse.link(queue_before_mux):
                        self.logger.error("Failed to link h264parse -> queue_before_mux")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking h264parse -> queue_before_mux: {link_err}")
                    link_ok = False
            
            if link_ok:
                try:
                    if not queue_before_mux.link(splitmuxsink):
                        self.logger.error("Failed to link queue_before_mux -> splitmuxsink")
                        link_ok = False
                except Exception as link_err:
                    self.logger.error(f"Exception linking queue_before_mux -> splitmuxsink: {link_err}")
                    link_ok = False
            
            if not link_ok:
                # Clean up partially linked elements
                self.logger.error("Failed to link recording branch elements, cleaning up...")
                try:
                    self._cleanup_recording_branch()
                except Exception as cleanup_err:
                    self.logger.error(f"Error during cleanup after failed linking: {cleanup_err}")
                raise RuntimeError("Failed to link recording branch elements")
            
            # Verify that all links are actually established
            # Check the entire chain from recording_queue to splitmuxsink
            try:
                recording_queue_src = recording_queue.get_static_pad("src")
                if not recording_queue_src:
                    raise RuntimeError("recording_queue has no src pad")
                
                peer = recording_queue_src.get_peer()
                if not peer:
                    raise RuntimeError("recording_queue src pad is not linked")
                
                videoconvert_elem = peer.get_parent()
                if videoconvert_elem != videoconvert:
                    raise RuntimeError(f"recording_queue is linked to wrong element: {videoconvert_elem.get_name() if videoconvert_elem else 'None'}")
                
                # Check the rest of the chain
                videoconvert_src = videoconvert.get_static_pad("src")
                if videoconvert_src:
                    x264enc_peer = videoconvert_src.get_peer()
                    if not x264enc_peer or x264enc_peer.get_parent() != x264enc:
                        raise RuntimeError("videoconvert is not properly linked to x264enc")
            except Exception as verify_err:
                self.logger.error(f"Failed to verify recording branch links: {verify_err}")
                try:
                    self._cleanup_recording_branch()
                except Exception as cleanup_err:
                    self.logger.error(f"Error during cleanup after verification failure: {cleanup_err}")
                raise RuntimeError(f"Recording branch verification failed: {verify_err}")
            
            # Sync state of elements with pipeline parent
            # This is safe to do when pipeline is NULL or READY, but may cause issues if PLAYING
            # We do it conditionally based on pipeline state
            # Note: This method is called from _init_pipeline() which already holds pipeline_lock, so we don't acquire it here
            ret, current_state, pending_state = self.pipeline.get_state(Gst.SECOND)
            if ret != Gst.StateChangeReturn.FAILURE:
                if current_state in (Gst.State.NULL, Gst.State.READY):
                    # Safe to sync state when pipeline is NULL or READY
                    try:
                        for elem in self._recording_elements:
                            elem.sync_state_with_parent()
                    except Exception as sync_err:
                        self.logger.warning(f"Failed to sync recording elements state: {sync_err}")
                        # Don't fail setup if sync fails - elements will sync automatically when pipeline goes to PLAYING
                else:
                    # Pipeline is PLAYING or PAUSED - elements will sync automatically when pipeline state changes
                    self.logger.debug("Pipeline is PLAYING/PAUSED - elements will sync automatically on state change")
            
            self.logger.info("Recording branch setup successfully")
            
        except Exception as e:
            self.logger.error(f"Error setting up recording branch: {e}", exc_info=True)
            raise
    
    def _cleanup_recording_branch(self):
        """Clean up recording branch elements"""
        try:
            
            # Stop periodic check thread
            if self._recording_check_thread:
                self._recording_check_stop = True
                if self._recording_check_thread.is_alive():
                    self._recording_check_thread.join(timeout=2.0)
                self._recording_check_thread = None
            
            # Clean up recording elements
            # Note: Try to acquire lock, but don't block if it's already held (e.g., during pipeline shutdown)
            # Standard threading.Lock doesn't support timeout, so we use non-blocking acquire
            pipeline = None
            try:
                # Try to acquire lock without blocking to avoid deadlock
                lock_acquired = self.pipeline_lock.acquire(blocking=False)
                try:
                    pipeline = self.pipeline
                finally:
                    if lock_acquired:
                        self.pipeline_lock.release()
                if not lock_acquired:
                    # Lock is held, get pipeline reference without lock (may be None, but that's OK)
                    # This is safe because we're only reading the reference, not modifying it
                    pipeline = self.pipeline
            except Exception:
                # Fallback: get pipeline reference without lock
                pipeline = self.pipeline
            
            if self._recording_elements:
                for elem in self._recording_elements:
                        try:
                            if not elem:
                                continue
                            
                            # Set element state to NULL before removing
                            # This will automatically unlink all pads - no need to unlink manually
                            try:
                                ret = elem.set_state(Gst.State.NULL)
                                if ret == Gst.StateChangeReturn.ASYNC:
                                    # Wait for state change to complete
                                    elem.get_state(Gst.CLOCK_TIME_NONE)
                            except Exception:
                                pass
                            
                            # Remove element from pipeline if pipeline exists
                            if pipeline:
                                try:
                                    # Check if element is still in pipeline before removing
                                    parent = elem.get_parent()
                                    if parent == pipeline:
                                        pipeline.remove(elem)
                                except Exception:
                                    # Element might already be removed or pipeline might be None
                                    pass
                            
                        except Exception:
                            pass
                
                self._recording_elements = []
            
            # Clear recording-related attributes
            self._recording_out_dir = None
            self._recording_checked_files = set()
            self._recording_check_stop = False
            self._recording_queue_elem = None
            
        except Exception as e:
            self.logger.error(f"Error cleaning up recording branch: {e}", exc_info=True)
    
    def _retrieve_frames(self) -> None:
        """
        Retrieve frames (not used in this implementation).
        
        GStreamer handles frame retrieval automatically via callbacks.
        """
        pass
    
    def default(self):
        """
        Default implementation for EvilEyeBase.
        """
        pass
    
    def init_impl(self, **kwargs):
        """
        Implementation of EvilEyeBase init_impl.
        """
        return self.init()
    
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
