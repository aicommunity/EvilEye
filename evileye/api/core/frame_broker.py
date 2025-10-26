import threading
from typing import Dict, Optional, Tuple
import time
from evileye.core.logger import get_module_logger


class FrameBroker:
    """
    Thread-safe storage of JPEG frames for multiple pipelines.
    Supports stream control for MJPEG streaming.
    """
    
    def __init__(self):
        self.logger = get_module_logger("api.frame_broker")
        self._lock = threading.Lock()  # provides thread-safe access to the dictionary
        self._frames: Dict[str, Tuple[bytes, float]] = {}  # dictionary for storing JPEG frames
        self._active_streams: Dict[str, threading.Event] = {}

    def publish_jpeg(self, pipeline_id: str, jpeg_bytes: bytes) -> None:
        """Publishing/updating a JPEG image in storage"""
        with self._lock:
            self._frames[pipeline_id] = (jpeg_bytes, time.time())
        self.logger.debug(f"Published frame for pipeline '{pipeline_id}'")

    def latest_jpeg(self, pipeline_id: str) -> Optional[bytes]:
        """Returns the last frame for the specified stream, or None if there is none."""
        with self._lock:
            item = self._frames.get(pipeline_id)
            if not item:
                available_pipelines = list(self._frames.keys())
                self.logger.debug(f"No frame available for pipeline '{pipeline_id}'. Available pipelines: {available_pipelines}")
                return None
            jpeg_data, timestamp = item
            self.logger.debug(f"Retrieved frame for pipeline '{pipeline_id}', size: {len(jpeg_data)} bytes, age: {time.time() - timestamp:.2f}s")
            return jpeg_data
    
    def start_stream(self, pipeline_id: str) -> threading.Event:
        """
        Register a new active stream and return its stop event.
        If stream already exists, returns the existing event.
        """
        with self._lock:
            if pipeline_id not in self._active_streams:
                self._active_streams[pipeline_id] = threading.Event()
                self.logger.info(f"Started stream for pipeline '{pipeline_id}'")
            return self._active_streams[pipeline_id]
    
    def stop_stream(self, pipeline_id: str) -> bool:
        """
        Stop the active stream for the given pipeline.
        Returns True if stream was active, False otherwise.
        """
        with self._lock:
            if pipeline_id in self._active_streams:
                self._active_streams[pipeline_id].set()
                del self._active_streams[pipeline_id]
                self.logger.info(f"Stopped stream for pipeline '{pipeline_id}'")
                return True
            self.logger.warning(f"No active stream found for pipeline '{pipeline_id}'")
            return False
    
    def is_stream_active(self, pipeline_id: str) -> bool:
        """Check if there is an active stream for the pipeline"""
        with self._lock:
            return pipeline_id in self._active_streams
    
    def get_stream_event(self, pipeline_id: str) -> Optional[threading.Event]:
        """Get the stop event for a stream, or None if not active"""
        with self._lock:
            return self._active_streams.get(pipeline_id)
    
    def clear_pipeline(self, pipeline_id: str) -> None:
        """Remove frames for a specific pipeline"""
        with self._lock:
            if pipeline_id in self._frames:
                del self._frames[pipeline_id]
                self.logger.info(f"Cleared frames for pipeline '{pipeline_id}'")
    
    def clear_all(self) -> None:
        """Remove all frames"""
        with self._lock:
            self._frames.clear()
            self.logger.info("Cleared all frames")


