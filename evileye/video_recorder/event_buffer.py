from __future__ import annotations

import threading
import time
from collections import deque
from typing import List, Tuple, Optional
import numpy as np

from evileye.core.logger import get_module_logger


class EventBuffer:
    """Circular buffer for storing video frames with timestamps for event-based recording.
    
    Stores frames in memory-efficient way using numpy arrays. Automatically cleans up
    old frames that exceed the required buffer duration.
    """
    
    def __init__(self, max_duration_seconds: float, fps: Optional[float] = None):
        """
        Initialize event buffer.
        
        Args:
            max_duration_seconds: Maximum duration to keep frames (should be >= event_pre_seconds + event_post_seconds)
            fps: Frames per second (used for capacity estimation, None = auto-detect)
        """
        self.logger = get_module_logger("event_buffer")
        self.max_duration_seconds = max_duration_seconds
        self.fps = fps
        
        # Circular buffer: deque of (frame: np.ndarray, timestamp: float)
        self.buffer: deque[Tuple[np.ndarray, float]] = deque(maxlen=None)  # Will set maxlen dynamically
        self.lock = threading.Lock()
        
        # Estimate capacity based on FPS and duration
        if fps and fps > 0:
            estimated_capacity = int(fps * max_duration_seconds * 1.2)  # 20% margin
            self.buffer = deque(maxlen=estimated_capacity)
            self.logger.debug(f"EventBuffer initialized with capacity ~{estimated_capacity} frames (fps={fps}, duration={max_duration_seconds}s)")
        else:
            # No FPS info, use dynamic sizing with cleanup
            self.buffer = deque(maxlen=None)
            self.logger.debug(f"EventBuffer initialized with dynamic capacity (duration={max_duration_seconds}s)")
    
    def add_frame(self, frame: np.ndarray, timestamp: Optional[float] = None) -> None:
        """
        Add a frame to the buffer.
        
        Args:
            frame: Frame as numpy array (BGR format, shape: [height, width, 3])
            timestamp: Timestamp in seconds (None = use current time)
        """
        if timestamp is None:
            timestamp = time.time()
        
        # Make a copy to avoid reference issues
        frame_copy = frame.copy()
        
        with self.lock:
            self.buffer.append((frame_copy, timestamp))
            self._cleanup_old_frames()
    
    def get_frames_before(self, timestamp: float, seconds: float) -> List[Tuple[np.ndarray, float]]:
        """
        Get frames from buffer that are before the given timestamp, within the specified duration.
        
        Args:
            timestamp: Reference timestamp in seconds
            seconds: How many seconds before timestamp to retrieve
            
        Returns:
            List of (frame, timestamp) tuples, ordered by timestamp (oldest first)
        """
        cutoff_time = timestamp - seconds
        result = []
        
        with self.lock:
            # Iterate from oldest to newest
            for frame, frame_ts in self.buffer:
                if cutoff_time <= frame_ts < timestamp:
                    result.append((frame.copy(), frame_ts))
        
        # Sort by timestamp (should already be sorted, but ensure it)
        result.sort(key=lambda x: x[1])
        return result
    
    def get_frames_after(self, timestamp: float, seconds: float) -> List[Tuple[np.ndarray, float]]:
        """
        Get frames from buffer that are after the given timestamp, within the specified duration.
        
        Args:
            timestamp: Reference timestamp in seconds
            seconds: How many seconds after timestamp to retrieve
            
        Returns:
            List of (frame, timestamp) tuples, ordered by timestamp (oldest first)
        """
        cutoff_time = timestamp + seconds
        result = []
        
        with self.lock:
            # Iterate from oldest to newest
            for frame, frame_ts in self.buffer:
                if timestamp <= frame_ts <= cutoff_time:
                    result.append((frame.copy(), frame_ts))
        
        # Sort by timestamp (should already be sorted, but ensure it)
        result.sort(key=lambda x: x[1])
        return result
    
    def get_frames_range(self, start_timestamp: float, end_timestamp: float) -> List[Tuple[np.ndarray, float]]:
        """
        Get frames from buffer within a time range.
        
        Args:
            start_timestamp: Start timestamp in seconds
            end_timestamp: End timestamp in seconds
            
        Returns:
            List of (frame, timestamp) tuples, ordered by timestamp (oldest first)
        """
        result = []
        
        with self.lock:
            for frame, frame_ts in self.buffer:
                if start_timestamp <= frame_ts <= end_timestamp:
                    result.append((frame.copy(), frame_ts))
        
        result.sort(key=lambda x: x[1])
        return result
    
    def _cleanup_old_frames(self) -> None:
        """Remove frames older than max_duration_seconds from the buffer."""
        if not self.buffer:
            return
        
        # Determine cutoff time based on buffer type
        # For absolute timestamps (live sources), use current time
        # For relative timestamps (video files), use newest timestamp
        newest_ts = self.buffer[-1][1] if self.buffer else None
        if newest_ts is None:
            return
        
        # If newest timestamp is large (> 1 day), it's absolute time (live source)
        # Otherwise it's relative time (video file)
        if newest_ts > 86400:  # Absolute timestamp (live source)
            current_time = time.time()
            cutoff_time = current_time - self.max_duration_seconds
        else:  # Relative timestamp (video file)
            cutoff_time = newest_ts - self.max_duration_seconds
        
        # Remove old frames from the left (oldest)
        # For buffers with maxlen, deque auto-removes, but we still clean up by timestamp
        # to ensure we don't keep frames beyond max_duration_seconds
        removed_count = 0
        while self.buffer and self.buffer[0][1] < cutoff_time:
            self.buffer.popleft()
            removed_count += 1
        
        if removed_count > 0:
            self.logger.debug(f"Cleaned up {removed_count} old frames from buffer (cutoff_time={cutoff_time:.3f})")
    
    def clear(self) -> None:
        """Clear all frames from the buffer."""
        with self.lock:
            self.buffer.clear()
    
    def size(self) -> int:
        """Get current number of frames in buffer."""
        with self.lock:
            return len(self.buffer)
    
    def get_oldest_timestamp(self) -> Optional[float]:
        """Get timestamp of oldest frame in buffer, or None if empty."""
        with self.lock:
            if not self.buffer:
                return None
            return self.buffer[0][1]
    
    def get_newest_timestamp(self) -> Optional[float]:
        """Get timestamp of newest frame in buffer, or None if empty."""
        with self.lock:
            if not self.buffer:
                return None
            return self.buffer[-1][1]
    
    def get_duration(self) -> float:
        """Get time span covered by buffer in seconds."""
        oldest = self.get_oldest_timestamp()
        newest = self.get_newest_timestamp()
        if oldest is None or newest is None:
            return 0.0
        return newest - oldest
    
    def clear_old_frames(self, older_than_seconds: Optional[float] = None) -> int:
        """
        Explicitly clear old frames from buffer.
        
        Args:
            older_than_seconds: Remove frames older than this many seconds from newest frame.
                                If None, uses max_duration_seconds.
        
        Returns:
            Number of frames removed
        """
        if not self.buffer:
            return 0
        
        if older_than_seconds is None:
            older_than_seconds = self.max_duration_seconds
        
        newest_ts = self.buffer[-1][1] if self.buffer else None
        if newest_ts is None:
            return 0
        
        # Determine cutoff time
        if newest_ts > 86400:  # Absolute timestamp
            current_time = time.time()
            cutoff_time = current_time - older_than_seconds
        else:  # Relative timestamp
            cutoff_time = newest_ts - older_than_seconds
        
        removed_count = 0
        with self.lock:
            while self.buffer and self.buffer[0][1] < cutoff_time:
                self.buffer.popleft()
                removed_count += 1
        
        if removed_count > 0:
            self.logger.debug(f"Explicitly cleared {removed_count} old frames (older than {older_than_seconds}s)")
        
        return removed_count