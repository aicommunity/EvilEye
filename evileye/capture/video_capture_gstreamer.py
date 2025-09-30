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
                pipeline = f"rtspsrc location={self.source_address} userid={self.username} passwd={self.password} ! rtph264depay ! h264parse ! avdec_h264 ! videoconvert"
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
                pipeline = f"filesrc location={self.source_address} ! decodebin ! videoconvert"
                   
            
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
        pipeline += " ! video/x-raw,format=BGR ! appsink name=sink emit-signals=true sync=false max-buffers=1 drop=true"
        
        return pipeline
    
    def _on_new_sample(self, appsink):
        """
        Callback for new frame from GStreamer pipeline.
        """
        try:
            sample = appsink.emit("pull-sample")
            if sample:
                buffer = sample.get_buffer()
                caps = sample.get_caps()
                
                # Get frame dimensions
                structure = caps.get_structure(0)
                width = structure.get_int("width")[1]
                height = structure.get_int("height")[1]
                
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
                    
                    # Store frame
                    with self.frame_lock:
                        self.last_frame = capture_image
                        self.frame_id_counter += 1
                    
                    # Notify subscribers
                    for subscriber in self.subscribers:
                        try:
                            if callable(subscriber):
                                subscriber(capture_image)
                            else:
                                # If subscriber is an object, try to call a method
                                if hasattr(subscriber, 'process_frame'):
                                    subscriber.process_frame(capture_image)
                                elif hasattr(subscriber, 'update'):
                                    subscriber.update()  # update() doesn't take parameters
                                else:
                                    self.logger.debug(f"Subscriber {type(subscriber)} has no callable methods")
                        except Exception as e:
                            self.logger.error(f"Error notifying subscriber {type(subscriber)}: {e}")
                    
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
                
                # Get appsink element
                self.appsink = self.pipeline.get_by_name("sink")
                if not self.appsink:
                    raise RuntimeError("Failed to get appsink element")
                
                # Connect callback
                self.appsink.connect("new-sample", self._on_new_sample)
                
                # Set pipeline to playing state
                ret = self.pipeline.set_state(Gst.State.PLAYING)
                if ret == Gst.StateChangeReturn.FAILURE:
                    raise RuntimeError("Failed to start GStreamer pipeline")
                elif ret == Gst.StateChangeReturn.ASYNC:
                    # Wait for state change to complete
                    ret = self.pipeline.get_state(Gst.CLOCK_TIME_NONE)
                    if ret[0] == Gst.StateChangeReturn.FAILURE:
                        raise RuntimeError("Failed to start GStreamer pipeline")
                
                self.logger.info("GStreamer pipeline initialized successfully")
                
        except Exception as e:
            self.logger.error(f"Failed to initialize GStreamer pipeline: {e}")
            self.logger.error(f"Pipeline string was: {pipeline_str}")
            raise
    
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
            with self.pipeline_lock:
                if self.pipeline:
                    self.pipeline.set_state(Gst.State.NULL)
                    self.pipeline = None
                
                self._stop_main_loop()
                
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
        """
        Implementation of EvilEyeBase get_params_impl.
        """
        return super().get_params_impl()
    
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
