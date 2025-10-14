import threading
from typing import Dict, Optional, Tuple
import time
from evileye.core.logger import get_module_logger


class FrameBroker:
    """Thread-safe storage of JPEG frames"""
    
    def __init__(self):
        self.logger = get_module_logger("api.frame_broker")
        self._lock = threading.Lock()  # provides thread-safe access to the dictionary
        self._frames: Dict[str, Tuple[bytes, float]] = {}  # dictionary for storing JPEG frames

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
                self.logger.debug(f"No frame available for pipeline '{pipeline_id}'")
                return None
            return item[0]


