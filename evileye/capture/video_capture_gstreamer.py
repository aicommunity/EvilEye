import cv2
import numpy as np
import threading
import time
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
            # IP Camera pipeline
            if self.username and self.password:
                pipeline = f"rtspsrc location={self.source_address} user-id={self.username} user-pw={self.password} ! rtph265depay ! h265parse ! avdec_h265 ! videoconvert"
            else:
                pipeline = f"rtspsrc location={self.source_address} ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
            
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
        # Use sync=true to play according to timestamps (real-time). Keep drop to avoid backlog.
        # Add final queue before sink to isolate sink during shutdown
        pipeline += " ! queue max-size-buffers=10 max-size-bytes=0 max-size-time=0 ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true wait-on-eos=false enable-last-sample=false sync=true max-buffers=1 drop=true"
        
        return pipeline
    
    def _on_new_sample(self, appsink):
        """
        Callback for new frame from GStreamer pipeline.
        """
        try:
            if not self.is_working:
                return Gst.FlowReturn.EOS
            sample = appsink.emit("pull-sample")
            if sample:
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
                    
                    # Create CaptureImage
                    capture_image = CaptureImage()
                    capture_image.image = frame_data
                    capture_image.frame_id = self.frame_id_counter
                    capture_image.time_stamp = time.time()
                    capture_image.source_id = self.source_ids[0] if self.source_ids else 0
                    # Update current video position/frame for GUI like OpenCV implementation
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
                        capture_image.current_video_frame = self.video_current_frame
                        capture_image.current_video_position = self.video_current_position
                    # Maintain rolling FPS estimate as fallback
                    now = capture_image.time_stamp
                    self._fps_times.append(now)
                    if len(self._fps_times) > 30:
                        self._fps_times.pop(0)
                    if self.source_fps is None and len(self._fps_times) >= 2:
                        dt = self._fps_times[-1] - self._fps_times[0]
                        if dt > 0:
                            self.source_fps = (len(self._fps_times) - 1) / dt
                    
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
    
    def _init_pipeline(self):
        """
        Initialize GStreamer pipeline.
        """
        try:
            with self.pipeline_lock:
                if self.pipeline:
                    self.pipeline.set_state(Gst.State.NULL)
                    self.pipeline = None
                
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
                
                # Set pipeline to playing state
                ret = self.pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError("Failed to start GStreamer pipeline")
                elif ret == Gst.StateChangeReturn.ASYNC:
                    # Wait for state change to complete
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
                
        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer pipeline: {e}")
            self.logger.error(f"Pipeline string was: {pipeline_str}")
            raise

    def _on_bus_message(self, bus, message):
        try:
            msg_type = message.type
            if msg_type == Gst.MessageType.EOS:
                self.logger.info("GStreamer EOS received")
                if self.source_type == CaptureDeviceType.VideoFile and self.loop_play:
                    self._seek_to_start()
                else:
                    self.finished = True
                    self.is_working = False
            elif msg_type == Gst.MessageType.ERROR:
                err, debug = message.parse_error()
                self.logger.error(f"GStreamer ERROR: {err}, debug: {debug}")
                self.is_working = False
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
        """
        if not self.gstreamer_available:
            self.logger.error("GStreamer not available, cannot initialize")
            self.is_inited = False
            self.is_working = False
            raise RuntimeError("GStreamer not available")
        
        try:
            self._init_pipeline()
            self._start_main_loop()
            self.is_inited = True
            self.is_working = True
            self.logger.info("GStreamer video capture initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer capture: {e}")
            self.is_inited = False
            self.is_working = False
            raise

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
        """
        frames = []
        if self.is_working and self.last_frame:
            with self.frame_lock:
                if self.last_frame:
                    frames.append(self.last_frame)
        return frames
    
    def _grab_frames(self):
        """
        Grab frames from GStreamer pipeline (not used in this implementation).
        """
        # GStreamer handles frame grabbing automatically via callbacks
        pass
    
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
