import cv2
import numpy as np
import threading
import time
import datetime
from typing import Optional, List
from queue import Queue, Empty
from .video_capture_base import VideoCaptureBase, CaptureDeviceType
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
        self.frame_buffer = Queue(maxsize=10)
        self.last_frame = None
        self.frame_lock = threading.Lock()
        self.pipeline_lock = threading.Lock()
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

    # Debug stack dump removed
    
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
            # Video file pipeline
            use_nv_decoder = (
                self._gst_has('nvv4l2decoder') and
                self._gst_has('nvvidconv') and
                str(self.source_address).lower().endswith('.mp4')
            )

            if use_nv_decoder:
                # Prefer NV hardware decode path on Jetson/NVIDIA systems
                pipeline = (
                    f"filesrc location={self.source_address} ! qtdemux ! h264parse ! nvv4l2decoder "
                    f"! nvvidconv ! video/x-raw(memory:NVMM),format=BGRx ! nvvidconv ! video/x-raw,format=BGRx ! videoconvert"
                )
            else:
                # Fallback: generic software decode supporting many containers/codecs
                # Add queues to decouple threads and avoid teardown stalls
                pipeline = f"filesrc location={self.source_address} ! decodebin name=dec ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! videoconvert ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0"
                   
            
        elif self.source_type == CaptureDeviceType.Device:
            # USB/Device camera pipeline
            device_id = self.source_address if self.source_address.isdigit() else "0"
            pipeline = f"v4l2src device=/dev/video{device_id} ! videoconvert"
            
        elif self.source_type == CaptureDeviceType.ImageSequence:
            # Image sequence pipeline - support for folders with jpeg, png, bmp
            # Check if source_address is a directory (no file mask)
            if not any(pattern in self.source_address for pattern in ['%', '*', '?']):
                # Directory path - use multifilesrc with wildcard pattern
                pipeline = f"multifilesrc location={self.source_address}/* ! decodebin ! videoconvert"
            else:
                # File pattern - use as is
                pipeline = f"multifilesrc location={self.source_address} ! decodebin ! videoconvert"
        
        else:
            raise ValueError(f"Unsupported source type: {self.source_type}")
        
        # Add common pipeline end - simplified
        # Apply desired FPS if requested using videorate (before format caps/appsink)
        if self.desired_fps and self.desired_fps > 0:
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
        # If recording is enabled, use tee to split stream: one to appsink, one to recording
        if self.recording_params and self.recording_params.enabled:
            # Use tee to split stream
            pipeline += " ! tee name=t"
            # Branch 1: to appsink for capture (with queue for isolation)
            pipeline += " t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true"
            # Branch 2: to recording (will be connected after pipeline creation)
            pipeline += " t. ! queue name=recording_queue"
        else:
            # No recording - direct to appsink
            pipeline += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true"
        
        return pipeline
    
    def _on_new_sample(self, appsink):
        """
        Callback for new frame from GStreamer pipeline.
        """
        try:
            sample = appsink.emit("pull-sample")
            if sample:
                # Mark as working when we receive first frame after init
                # Allow processing frames even if is_working is False (within 5 seconds of init)
                if self._init_time and not self.is_working:
                    now = time.time()
                    if (now - self._init_time) < 5.0:  # Within 5 seconds of init
                        self.logger.debug(f"First frame received {(now - self._init_time):.1f}s after init - marking as working")
                        self.is_working = True
                
                # If still not working after init grace period, skip frame
                if not self.is_working:
                    return Gst.FlowReturn.OK  # Return OK to continue, but don't process frame
                
                buffer = sample.get_buffer()
                caps = sample.get_caps()
                
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
                
                # Extract frame data
                success, map_info = buffer.map(Gst.MapFlags.READ)
                if success:
                    # Convert buffer to numpy array
                    frame_data = np.frombuffer(map_info.data, dtype=np.uint8)
                    frame_data = frame_data.reshape((height, width, 3))
                    
                    # Make array writable for OpenCV operations
                    frame_data = frame_data.copy()
                    
                    # Get current video position/frame for GUI like OpenCV implementation
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
                    
                    # Maintain rolling FPS estimate as fallback
                    now = time.time()
                    self._fps_times.append(now)
                    if len(self._fps_times) > 30:
                        self._fps_times.pop(0)
                    if self.source_fps is None and len(self._fps_times) >= 2:
                        dt = self._fps_times[-1] - self._fps_times[0]
                        if dt > 0:
                            self.source_fps = (len(self._fps_times) - 1) / dt
                    
                    # Handle split_stream - create multiple CaptureImage objects from single frame
                    if self.split_stream and self.src_coords and self.num_split > 0:
                        # Create multiple CaptureImage objects for split streams
                        capture_images = []
                        for stream_cnt in range(self.num_split):
                            if stream_cnt < len(self.src_coords):
                                # Extract region from frame using src_coords
                                x, y, w, h = self.src_coords[stream_cnt]
                                # Ensure coordinates are integers
                                x, y, w, h = int(x), int(y), int(w), int(h)
                                # Extract region: [y:y+h, x:x+w]
                                region = frame_data[y:y+h, x:x+w].copy()
                                
                                # Create CaptureImage for this split region
                                capture_image = CaptureImage()
                                capture_image.image = region
                                capture_image.frame_id = self.frame_id_counter
                                capture_image.time_stamp = now
                                capture_image.source_id = self.source_ids[stream_cnt] if self.source_ids and stream_cnt < len(self.source_ids) else stream_cnt
                                capture_image.current_video_frame = current_video_frame
                                capture_image.current_video_position = current_video_position
                                capture_images.append(capture_image)
                        
                        # Store all frames in frame_buffer
                        with self.frame_lock:
                            for img in capture_images:
                                self.frame_buffer.put(img, block=False)
                            # Store first frame as last_frame for compatibility
                            if capture_images:
                                self.last_frame = capture_images[0]
                            self.frame_id_counter += 1
                        
                        # Notify subscribers asynchronously for each split frame
                        for capture_image in capture_images:
                            def _notify(sub, img=capture_image):
                                try:
                                    if callable(sub):
                                        sub(img)
                                    else:
                                        if hasattr(sub, 'process_frame'):
                                            sub.process_frame(img)
                                except Exception as ex:
                                    try:
                                        self.logger.error(f"Error notifying subscriber {type(sub)}: {ex}")
                                    except Exception:
                                        pass
                            for sub in self.subscribers:
                                threading.Thread(target=_notify, args=(sub,), daemon=True).start()
                    else:
                        # Single stream - create one CaptureImage
                        capture_image = CaptureImage()
                        capture_image.image = frame_data
                        capture_image.frame_id = self.frame_id_counter
                        capture_image.time_stamp = now
                        capture_image.source_id = self.source_ids[0] if self.source_ids else 0
                        capture_image.current_video_frame = current_video_frame
                        capture_image.current_video_position = current_video_position
                        
                        # Store frame
                        with self.frame_lock:
                            self.last_frame = capture_image
                            self.frame_id_counter += 1
                        
                        # Notify subscribers asynchronously to avoid blocking appsink thread
                        def _notify(sub):
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
                        for subscriber in self.subscribers:
                            threading.Thread(target=_notify, args=(subscriber,), daemon=True).start()
                    
                    buffer.unmap(map_info)
                    return Gst.FlowReturn.OK
                else:
                    self.logger.error("Failed to map buffer")
                    return Gst.FlowReturn.ERROR
        except Exception as e:
            self.logger.error(f"Error processing frame: {e}")
            return Gst.FlowReturn.ERROR
    
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
        common_tail = " ! videoconvert"
        if self.recording_params and self.recording_params.enabled:
            common_tail += " ! tee name=t"
            common_tail += " t. ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true"
            common_tail += " t. ! queue name=recording_queue"
        else:
            common_tail += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true"
        
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
                                self.logger.debug(f"GStreamer pipeline (candidate): {candidate_str}")
                            else:
                                self.logger.info(f"GStreamer pipeline: {candidate_str}")
                            
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
                            
                            # Setup recording branch if enabled
                            if self.recording_params and self.recording_params.enabled:
                                try:
                                    self._setup_recording_branch()
                                except Exception as e:
                                    self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                                    # Continue without recording
                            
                            # Set pipeline to playing state - simple approach from api-refactoring
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
                    self.logger.info(f"GStreamer pipeline: {pipeline_str}")
                    
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
                    
                    # Setup recording branch if enabled
                    if self.recording_params and self.recording_params.enabled:
                        try:
                            self._setup_recording_branch()
                        except Exception as e:
                            self.logger.error(f"Failed to setup recording branch: {e}", exc_info=True)
                            # Continue without recording
                    
                    # Set pipeline to playing state - simple approach from api-refactoring
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
                
        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer pipeline: {e}")
            if pipeline_str:
                self.logger.error(f"Pipeline string was: {pipeline_str}")
            raise

    def _on_bus_message(self, bus, message):
        try:
            msg_type = message.type
            if msg_type == Gst.MessageType.EOS:
                self.logger.info("GStreamer EOS received")
                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    try:
                        # Restart pipeline instead of seek to avoid TIME/BYTES format mismatch
                        with self.pipeline_lock:
                            try:
                                if self.pipeline is not None:
                                    self.pipeline.set_state(Gst.State.NULL)
                            except Exception:
                                pass
                            self.pipeline = None
                        time.sleep(0.1)
                        self._init_pipeline()
                        self.logger.info("Looping video: pipeline restarted")
                    except Exception as e:
                        self.logger.error(f"Loop restart failed: {e}")
                elif self.source_type == CaptureDeviceType.IpCamera:
                    # For IP cameras, EOS means disconnect - but ignore early EOS (within 5 seconds of init)
                    # This prevents false positives when pipeline is still initializing
                    now = time.time()
                    if self._init_time and (now - self._init_time) < 5.0:
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
                    if self.run_flag and not (hasattr(self, '_reconnecting') and self._reconnecting):
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
                    if not (hasattr(self, '_reconnecting') and self._reconnecting):
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
            elif msg_type == Gst.MessageType.WARNING:
                warn, debug = message.parse_warning()
                # Check for UDP-related warnings
                if "UDP" in str(warn) or "udp" in str(warn).lower() or "Error sending" in str(warn):
                    self.logger.warning(f"GStreamer pipeline WARNING: {warn}, debug: {debug}")
                    if self.source_type == CaptureDeviceType.IpCamera:
                        self._last_init_error = RuntimeError(f"UDP connection error: {warn}: {debug}")
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
                if hasattr(self, '_recording_check_thread') and self._recording_check_thread and not self._recording_check_thread.is_alive():
                    self._recording_check_thread.start()
                
                return True
            except Exception as e:
                self.logger.error(f"Failed to initialize GStreamer capture: {e}")
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
            self.logger.debug(f"Checking recording: params={self.recording_params is not None}, enabled={self.recording_params.enabled if self.recording_params else False}")
            if self.recording_params and self.recording_params.enabled:
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
    
    def release(self):
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
                            if hasattr(self, '_appsink_handler_id') and self._appsink_handler_id is not None:
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

            # Clean frames and flags
            with self.frame_lock:
                self.last_frame = None

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
        For single stream, returns last_frame.
        """
        frames = []
        if not self.is_working:
            return frames
        
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
            # For single stream, return last_frame
            with self.frame_lock:
                if self.last_frame:
                    frames.append(self.last_frame)
        
        return frames
    
    def _grab_frames(self):
        """
        Monitor pipeline state and reconnect if needed (similar to OpenCV reconnect logic).
        """
        while self.run_flag:
            if not self.is_inited or self.pipeline is None:
                # For IP cameras, use reconnect loop instead of direct init()
                if self.source_type == CaptureDeviceType.IpCamera:
                    if not (hasattr(self, '_reconnecting') and self._reconnecting):
                        self.logger.info(f"Source {self.source_names} not initialized, starting reconnect loop")
                        threading.Thread(target=self._reconnect_loop, daemon=True).start()
                    # Wait a bit before checking again
                    time.sleep(2.0)
                else:
                    # For video files, try direct init
                    time.sleep(0.1)
                    if self.run_flag:
                        try:
                            if self.init():
                                timestamp = datetime.datetime.now()
                                self.logger.info(f"Reconnected to source: {self.source_names}")
                                self.reconnects.append((self.source_address, timestamp, self.is_working))
                                for sub in self.subscribers:
                                    sub.update()
                        except Exception as e:
                            self.logger.error(f"Reconnection failed: {e}")
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
                            with self.frame_lock:
                                last_frame_time = getattr(self.last_frame, 'time_stamp', 0) if self.last_frame else 0
                            now = time.time()
                            if last_frame_time > 0 and (now - last_frame_time) > 15.0:
                                # No frames for 15 seconds - mark as not working
                                if self.is_working:
                                    self.logger.warning(f"Pipeline PLAYING but no frames received after 10s, marking as not working")
                                    self.is_working = False
                        else:
                            self.is_working = False
            except Exception as e:
                self.logger.debug(f"Error checking pipeline state: {e}")
            
            # Check if pipeline is still working
            if not self.is_working and self.source_type == CaptureDeviceType.IpCamera:
                # Try to reconnect (but don't create multiple threads)
                if self.run_flag and not (hasattr(self, '_reconnecting') and self._reconnecting):
                    self.logger.info(f"Pipeline not working, starting reconnect loop for {self.source_names}")
                    threading.Thread(target=self._reconnect_loop, daemon=True).start()
            
            # Sleep according to monitor interval
            try:
                cfg = (self.params or {}).get('reconnect', {}) if hasattr(self, 'params') else {}
                monitor_sleep = float(cfg.get('monitor_interval_sec', 2.0))
            except Exception:
                monitor_sleep = 2.0
            time.sleep(monitor_sleep)
    
    def _reconnect_loop(self):
        """Reconnect loop for IP cameras (similar to OpenCV _grab_frames reconnect logic)"""
        if not self.run_flag:
            return
        # Prevent multiple simultaneous reconnect attempts
        if hasattr(self, '_reconnecting') and self._reconnecting:
            return
        self._reconnecting = True
        try:
            # Prevent races with monitor thread and force not working state
            self.is_inited = False
            self.is_working = False
            # Read reconnect settings from params if provided
            try:
                cfg = (self.params or {}).get('reconnect', {}) if hasattr(self, 'params') else {}
            except Exception:
                cfg = {}
            max_attempts = int(cfg.get('max_attempts', 0))  # 0 => infinite by default
            initial_delay_sec = float(cfg.get('initial_delay_sec', 8.0))
            max_delay_sec = float(cfg.get('max_delay_sec', 60.0))
            backoff_step_sec = float(cfg.get('backoff_step_sec', 6.0))
            attempt = 0
            while self.run_flag and (max_attempts == 0 or attempt < max_attempts):
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
        if not self.recording_params or not self.recording_params.enabled:
            return
        
        try:
            self.logger.debug("Setting up recording branch...")
            # Clean up existing recording branch if any (prevent duplicates)
            if hasattr(self, '_recording_elements') and self._recording_elements:
                self.logger.debug("Cleaning up existing recording branch...")
                self._cleanup_recording_branch()
            
            from pathlib import Path
            import datetime as _dt
            
            # Get recording queue element
            self.logger.debug("Getting recording_queue element...")
            recording_queue = self.pipeline.get_by_name("recording_queue")
            if not recording_queue:
                raise RuntimeError("Failed to get recording_queue element")
            
            # Create recording elements
            self.logger.debug("Creating recording elements...")
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
            
            # Build output path with camera name subfolder
            date_dir = _dt.datetime.now().strftime("%Y-%m-%d")
            
            # Compose camera folder name from all source_names or source_ids
            if self.source_names and len(self.source_names) > 0:
                camera_folder = "-".join(self.source_names)
            elif self.source_ids and len(self.source_ids) > 0:
                camera_folder = "-".join(str(sid) for sid in self.source_ids)
            else:
                camera_folder = "source"
            
            # Create path: out_dir/YYYY-MM-DD/CameraName/
            base_out_dir = Path(self.recording_params.out_dir) if self.recording_params.out_dir else Path(".")
            out_dir = base_out_dir / date_dir / camera_folder
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
                        if not hasattr(self, '_recording_out_dir') or not self._recording_out_dir or not self._recording_out_dir.exists():
                            time.sleep(5.0)
                            continue
                        
                        # Get all video files in recording directory
                        from evileye.video_recorder.utils import check_and_delete_small_files
                        for file_path in self._recording_out_dir.glob(f"*.{self._recording_container}"):
                            if file_path in self._recording_checked_files:
                                continue
                            
                            # Try to delete small/invalid files (only if not active per util's min_age rule)
                            deleted = check_and_delete_small_files(file_path, self._recording_min_file_size_kb)
                            if deleted:
                                reason = "invalid name pattern" if '%' in file_path.name else f"size < {self._recording_min_file_size_kb} KB"
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
            
            # Add elements to pipeline
            self.pipeline.add(videoconvert)
            self.pipeline.add(x264enc)
            self.pipeline.add(h264parse)
            self.pipeline.add(queue_before_mux)
            self.pipeline.add(splitmuxsink)
            
            # Link elements
            recording_queue.link(videoconvert)
            videoconvert.link(x264enc)
            x264enc.link(h264parse)
            h264parse.link(queue_before_mux)
            queue_before_mux.link(splitmuxsink)
            
            # Elements will sync state automatically when pipeline state changes
            # Don't call sync_state_with_parent() here to avoid deadlocks
            
            self.logger.info("Recording branch setup successfully")
            
        except Exception as e:
            self.logger.error(f"Error setting up recording branch: {e}", exc_info=True)
            raise
    
    def _cleanup_recording_branch(self):
        """Clean up recording branch elements"""
        try:
            # Stop periodic check thread
            if hasattr(self, '_recording_check_thread') and self._recording_check_thread:
                self._recording_check_stop = True
                if self._recording_check_thread.is_alive():
                    self._recording_check_thread.join(timeout=2.0)
                self._recording_check_thread = None
            
            # Clean up recording elements
            if hasattr(self, '_recording_elements') and self._recording_elements:
                for elem in self._recording_elements:
                    try:
                        if elem:
                            elem.set_state(Gst.State.NULL)
                            if self.pipeline:
                                self.pipeline.remove(elem)
                    except Exception as e:
                        self.logger.debug(f"Error removing recording element: {e}")
                self._recording_elements = []
            
            # Clear recording-related attributes
            self._recording_out_dir = None
            self._recording_checked_files = set()
            self._recording_check_stop = False
        except Exception as e:
            self.logger.debug(f"Error cleaning up recording branch: {e}")
    
    def _retrieve_frames(self):
        """
        Retrieve frames (not used in this implementation).
        """
        # GStreamer handles frame retrieval automatically via callbacks
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
            params['source_fps'] = self.source_fps
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
