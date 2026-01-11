from __future__ import annotations

import cv2
import time
import threading
import queue
from pathlib import Path
from typing import Optional, List, Tuple
from datetime import datetime
import numpy as np

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.event_buffer import EventBuffer
from evileye.video_recorder.recorder_base import SourceMeta


class EventRecorder:
    """Records video clips around events (pre-event and post-event frames)."""
    
    def __init__(self, source_meta: SourceMeta, params: RecordingParams, event_buffer: EventBuffer):
        """
        Initialize event recorder.
        
        Args:
            source_meta: Source metadata
            params: Recording parameters
            event_buffer: Event buffer to get pre-event frames from
        """
        self.logger = get_module_logger("event_recorder")
        self.source = source_meta
        self.params = params
        self.event_buffer = event_buffer
        
        self._writer: Optional[cv2.VideoWriter] = None
        self._lock = threading.Lock()
        self._frame_size = (0, 0)
        self._fps = float(source_meta.fps or 25.0)
        self._current_file_path: Optional[Path] = None
        self._is_recording = False
        self._event_start_time: Optional[float] = None
        self._event_id: Optional[int] = None
        self._event_name: Optional[str] = None
        self._pre_event_frames: List[Tuple[np.ndarray, float]] = []
        self._post_event_frame_count = 0
        self._max_post_frames = int(self._fps * params.event_post_seconds) if self._fps > 0 else 0
        self._frame_interval = 1.0 / self._fps if self._fps > 0 else 0.04  # Target interval between frames in seconds
        self._last_written_timestamp: Optional[float] = None  # Last timestamp of written frame
        
        # Async recording attributes
        self._recording_thread: Optional[threading.Thread] = None
        # Limit queue size to prevent memory leaks (100 frames should be enough for ~4 seconds at 25fps)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=100)
        self._stop_recording: threading.Event = threading.Event()
    
    def _fourcc_candidates(self, container: str) -> List[str]:
        """Get codec candidates for container."""
        c = container.lower()
        if c == "mp4":
            return ["mp4v", "avc1", "H264", "X264"]
        return ["XVID", "MJPG", "mp4v", "H264"]
    
    def _get_event_output_path(self, event_id: int, event_name: str, event_timestamp: float) -> Path:
        """Generate output path for event recording."""
        event_date = datetime.fromtimestamp(event_timestamp).strftime("%Y-%m-%d")
        event_time = datetime.fromtimestamp(event_timestamp).strftime("%Y%m%d_%H%M%S")
        
        # Compose camera folder name
        if self.source.source_names and len(self.source.source_names) > 0:
            camera_folder = "-".join(self.source.source_names)
        elif self.source.source_ids and len(self.source.source_ids) > 0:
            camera_folder = "-".join(str(sid) for sid in self.source.source_ids)
        else:
            camera_folder = self.source.source_name
        
        # Create path: Events/YYYY-MM-DD/Videos/CameraName/
        # Get base directory from out_dir (extract parent if it contains Streams)
        base_out_dir = Path(self.params.out_dir) if self.params.out_dir else Path(".")
        # If out_dir ends with Streams, extract base (EvilEyeData)
        # If out_dir contains Streams/YYYY-MM-DD, extract base (EvilEyeData)
        # Otherwise assume out_dir is already the base
        parts = base_out_dir.parts
        if len(parts) >= 1 and parts[-1] == 'Streams':
            # out_dir = "EvilEyeData/Streams" -> base = "EvilEyeData"
            base_dir = Path(*parts[:-1]) if len(parts) > 1 else Path('EvilEyeData')
        elif len(parts) >= 2 and parts[-2] == 'Streams':
            # out_dir = "EvilEyeData/Streams/2026-01-04" -> base = "EvilEyeData"
            base_dir = Path(*parts[:-2]) if len(parts) > 2 else Path('EvilEyeData')
        else:
            base_dir = base_out_dir.parent if base_out_dir.parent != Path('.') else Path('EvilEyeData')
        out_dir = base_dir / "Events" / event_date / "Videos" / camera_folder
        out_dir.mkdir(parents=True, exist_ok=True)
        
        source_name = (self.source.source_names[0] if self.source.source_names else 
                       (self.source.source_name if self.source else "source"))
        filename = f"{source_name}_{event_name}_{event_id}_{event_time}.{self.params.container}"
        
        return out_dir / filename
    
    def _open_writer(self, output_path: Path, frame_size: Tuple[int, int]) -> bool:
        """Open video writer for event recording."""
        containers_to_try = [self.params.container]
        if self.params.container.lower() != "mkv":
            containers_to_try.append("mkv")
        
        for cont in containers_to_try:
            for fourcc_code in self._fourcc_candidates(cont):
                try:
                    # Adjust extension if container differs
                    if cont != self.params.container:
                        output_path = output_path.with_suffix(f".{cont}")
                    
                    fourcc = cv2.VideoWriter_fourcc(*fourcc_code)
                    writer = cv2.VideoWriter(
                        str(output_path),
                        fourcc,
                        self._fps,
                        frame_size
                    )
                    
                    if writer.isOpened():
                        self._writer = writer
                        self._current_file_path = output_path
                        self.logger.info(f"Event recorder opened: {output_path} (codec={fourcc_code}, fps={self._fps})")
                        return True
                    else:
                        writer.release()
                except Exception as e:
                    self.logger.debug(f"Failed to open writer with {fourcc_code}: {e}")
                    continue
        
        self.logger.error(f"Failed to open event recorder writer for {output_path}")
        return False
    
    def _recording_worker(self) -> None:
        """
        Worker function for async recording thread.
        Writes pre-event frames with proper timing, then processes post-event frames from queue.
        """
        try:
            # Write pre-event frames with proper FPS timing
            sorted_frames = sorted(self._pre_event_frames, key=lambda x: x[1])
            last_written_time = None
            
            if sorted_frames:
                # Write first frame immediately
                first_frame, first_timestamp = sorted_frames[0]
                with self._lock:
                    if self._writer:
                        self._writer.write(first_frame)
                last_written_time = first_timestamp
                self.logger.debug(f"Written first pre-event frame at {first_timestamp:.3f}s")
                
                # Write subsequent frames with proper timing
                for frame, frame_timestamp in sorted_frames[1:]:
                    if self._stop_recording.is_set():
                        break
                    
                    # Calculate real time difference between frames
                    time_diff = frame_timestamp - last_written_time
                    
                    # Calculate how many frames should be written based on time difference
                    # This ensures output video has correct FPS regardless of input frame rate
                    expected_frames = max(1, int(round(time_diff / self._frame_interval)))
                    
                    # Write the frame (or duplicate it if needed to fill gaps)
                    for _ in range(expected_frames):
                        if self._stop_recording.is_set():
                            break
                        with self._lock:
                            if self._writer:
                                self._writer.write(frame)
                    
                    last_written_time = frame_timestamp
                
                self.logger.info(f"Written {len(sorted_frames)} pre-event frames")
                # Clear pre-event frames to free memory after writing
                self._pre_event_frames.clear()
            else:
                # No pre-event frames, set last timestamp to event time
                last_written_time = self._event_start_time
            
            # Process post-event frames from queue
            self.logger.debug("Starting to process post-event frames from queue")
            while not self._stop_recording.is_set():
                try:
                    # Get frame from queue with timeout
                    frame_data = self._frame_queue.get(timeout=0.1)
                    frame, frame_timestamp = frame_data
                    
                    # Check if we've exceeded post-event duration
                    elapsed_time = frame_timestamp - self._event_start_time
                    if elapsed_time >= self.params.event_post_seconds:
                        self.logger.info(f"Post-event duration exceeded: elapsed={elapsed_time:.2f}s, limit={self.params.event_post_seconds}s, stopping recording")
                        break
                    
                    # Write frame with proper timing
                    # Calculate how many frames to write based on time difference
                    if last_written_time is not None:
                        time_diff = frame_timestamp - last_written_time
                        # Calculate how many frames should be written based on time difference
                        # This ensures output video has correct FPS regardless of input frame rate
                        expected_frames = max(1, int(round(time_diff / self._frame_interval)))
                    else:
                        expected_frames = 1
                    
                    # Write the frame (or duplicate it if needed to fill gaps)
                    for _ in range(expected_frames):
                        if self._stop_recording.is_set():
                            break
                        with self._lock:
                            if self._writer:
                                # Validate and resize frame if needed
                                h, w = frame.shape[:2]
                                if self._frame_size != (w, h):
                                    frame = cv2.resize(frame, self._frame_size)
                                self._writer.write(frame)
                                self._post_event_frame_count += 1
                    
                    last_written_time = frame_timestamp
                    
                except queue.Empty:
                    # Check if we should continue waiting
                    if self._event_start_time and (time.time() - self._event_start_time) >= self.params.event_post_seconds:
                        break
                    continue
                except Exception as e:
                    self.logger.error(f"Error processing post-event frame: {e}", exc_info=True)
                    continue
                    
        except Exception as e:
            self.logger.error(f"Error in recording worker: {e}", exc_info=True)
        finally:
            self.logger.debug("Recording worker finished")
    
    def start_event_recording(self, event_id: int, event_name: str, event_timestamp: float, 
                              source_id: int, bbox: Optional[List] = None) -> tuple[bool, Optional[str]]:
        """
        Start recording an event.
        
        Args:
            event_id: Unique event ID
            event_name: Name of the event
            event_timestamp: Timestamp when event occurred
            source_id: Source ID where event occurred
            bbox: Optional bounding box of the event
            
        Returns:
            Tuple of (success: bool, relative_video_path: Optional[str])
            relative_video_path is relative to base_dir (e.g., "EvilEyeData")
        """
        with self._lock:
            if self._is_recording:
                self.logger.warning(f"Event recording already in progress, skipping event {event_id}")
                return False, None
            
            # Get pre-event frames from buffer
            self._pre_event_frames = self.event_buffer.get_frames_before(
                event_timestamp, 
                self.params.event_pre_seconds
            )
            
            if not self._pre_event_frames:
                self.logger.warning(f"No pre-event frames found for event {event_id}, recording anyway")
            
            # Determine if we're using relative timestamps (video files) or absolute (live sources)
            # Check the first frame timestamp to determine the type
            if self._pre_event_frames:
                first_frame_ts = self._pre_event_frames[0][1]
                last_frame_ts = self._pre_event_frames[-1][1]
                
                # If timestamps are small (< 1 day), they're likely relative (video files)
                # If timestamps are large, they're absolute (live sources)
                if first_frame_ts < 86400:  # Less than 1 day = likely relative timestamps
                    # Video file: use relative timestamps
                    # Event time is approximately at the end of pre-event frames
                    # Use last pre-event frame timestamp + one frame interval as event start
                    self._event_start_time = last_frame_ts + self._frame_interval
                    self.logger.debug(f"Using relative timestamps for video file: event_start_time={self._event_start_time:.3f}s")
                else:
                    # Live source: use absolute timestamps
                    self._event_start_time = event_timestamp
                    self.logger.debug(f"Using absolute timestamps for live source: event_start_time={self._event_start_time:.3f}s")
            else:
                # No pre-event frames, use event_timestamp as-is
                # Try to determine if it's relative or absolute
                if event_timestamp < 86400:  # Less than 1 day = likely relative
                    self._event_start_time = event_timestamp
                else:
                    self._event_start_time = event_timestamp
            
            # Determine frame size from first available frame
            frame_size = None
            if self._pre_event_frames:
                h, w = self._pre_event_frames[0][0].shape[:2]
                frame_size = (w, h)
            elif self.source.width and self.source.height:
                frame_size = (int(self.source.width), int(self.source.height))
            else:
                # Try to get frame size from buffer (any frame, not just pre-event)
                # This handles case when event happens before buffer is filled
                try:
                    with self.event_buffer.lock:
                        if len(self.event_buffer.buffer) > 0:
                            # Get any frame from buffer to determine size
                            any_frame, _ = self.event_buffer.buffer[-1]  # Get most recent frame
                            h, w = any_frame.shape[:2]
                            frame_size = (w, h)
                            self.logger.debug(f"Using frame size from buffer: {frame_size}")
                except Exception as e:
                    self.logger.debug(f"Could not get frame size from buffer: {e}")
            
            if frame_size is None:
                self.logger.warning(f"Cannot determine frame size for event {event_id}, will try to determine from first post-event frame")
                # Set a temporary size, will be updated when first frame arrives
                frame_size = (1920, 1080)  # Default fallback, will be corrected by first frame
            
            # Generate output path
            output_path = self._get_event_output_path(event_id, event_name, event_timestamp)
            
            # Calculate relative path (relative to base_dir, e.g., "EvilEyeData")
            # Extract base_dir from output_path
            # output_path format: base_dir/Events/YYYY-MM-DD/Videos/CameraName/filename.mp4
            # We need: Events/YYYY-MM-DD/Videos/CameraName/filename.mp4
            relative_video_path = None
            try:
                # Find base_dir by looking for "Events" in path
                path_parts = output_path.parts
                if 'Events' in path_parts:
                    events_idx = path_parts.index('Events')
                    relative_parts = path_parts[events_idx:]
                    relative_video_path = str(Path(*relative_parts))
                else:
                    # Fallback: use relative path from current working directory
                    # This shouldn't happen, but handle it gracefully
                    self.logger.warning(f"Could not determine relative path for video: {output_path}")
                    relative_video_path = str(output_path)
            except Exception as e:
                self.logger.warning(f"Error calculating relative video path: {e}")
                relative_video_path = str(output_path)
            
            # Open writer
            if not self._open_writer(output_path, frame_size):
                return False, None
            
            # Initialize recording state
            self._is_recording = True
            self._event_id = event_id
            self._event_name = event_name
            self._post_event_frame_count = 0
            
            # Clear queue and reset stop event
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break
            self._stop_recording.clear()
            
            # Start recording thread
            self._recording_thread = threading.Thread(
                target=self._recording_worker,
                daemon=True,
                name=f"EventRecorder-{event_id}"
            )
            self._recording_thread.start()
            
            self.logger.info(f"Started event recording: event_id={event_id}, event_name={event_name}, "
                           f"pre_frames={len(self._pre_event_frames)}, event_start_time={self._event_start_time:.3f}s, "
                           f"pre_seconds={self.params.event_pre_seconds}s, post_seconds={self.params.event_post_seconds}s, "
                           f"output={output_path}, relative_path={relative_video_path}")
            return True, relative_video_path
    
    def add_post_event_frame(self, frame: np.ndarray, timestamp: Optional[float] = None) -> bool:
        """
        Add a post-event frame to the recording queue.
        
        Args:
            frame: Frame as numpy array (BGR format)
            timestamp: Timestamp of the frame (required for FPS control)
            
        Returns:
            True if frame was added to queue, False if recording should stop
        """
        if not self._is_recording:
            return False
        
        # Check if we've recorded enough post-event frames (by time, not count)
        if timestamp is not None and self._event_start_time is not None:
            elapsed_time = timestamp - self._event_start_time
            if elapsed_time >= self.params.event_post_seconds:
                self.logger.debug(f"Post-event duration exceeded in add_post_event_frame: elapsed={elapsed_time:.2f}s, limit={self.params.event_post_seconds}s")
                return False
        elif self._max_post_frames > 0:
            with self._lock:
                if self._post_event_frame_count >= self._max_post_frames:
                    return False
        
        # If no timestamp provided, use current time (fallback)
        if timestamp is None:
            timestamp = time.time()
        
        # Validate frame size (store for later use in worker)
        h, w = frame.shape[:2]
        with self._lock:
            if self._frame_size == (0, 0) or self._frame_size == (1920, 1080):  # Fallback size
                # Update frame size and reopen writer if needed
                old_size = self._frame_size
                self._frame_size = (w, h)
                if old_size == (1920, 1080) and self._writer and self._current_file_path:
                    # Reopen writer with correct size
                    self.logger.info(f"Reopening writer with correct frame size: {self._frame_size}")
                    self._writer.release()
                    if not self._open_writer(self._current_file_path, self._frame_size):
                        self.logger.error("Failed to reopen writer with correct size")
                        return False
        
        # Add frame to queue (non-blocking)
        try:
            self._frame_queue.put_nowait((frame.copy(), timestamp))
            return True
        except queue.Full:
            # Queue is full - try to remove oldest frame and add new one
            try:
                # Remove oldest frame to make room
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    pass
                # Try to add new frame again
                try:
                    self._frame_queue.put_nowait((frame.copy(), timestamp))
                    self.logger.debug("Frame queue was full, dropped oldest frame and added new one")
                except queue.Full:
                    self.logger.warning("Frame queue is still full after removing oldest frame, dropping new frame")
            except Exception as e:
                self.logger.debug(f"Error handling full queue: {e}")
            return True  # Continue recording, just drop this frame
    
    def stop_event_recording(self) -> Optional[Path]:
        """
        Stop event recording and finalize file.
        
        Returns:
            Path to recorded file, or None if recording failed
        """
        with self._lock:
            if not self._is_recording:
                return None
            
            # Signal recording thread to stop
            self._stop_recording.set()
            self._is_recording = False
        
        # Wait for recording thread to finish (with timeout)
        if self._recording_thread and self._recording_thread.is_alive():
            self._recording_thread.join(timeout=5.0)
            if self._recording_thread.is_alive():
                self.logger.warning("Recording thread did not finish in time")
        
        # Close writer
        with self._lock:
            output_path = self._current_file_path
            
            if self._writer:
                self._writer.release()
                self._writer = None
            
            # Clear queue
            while not self._frame_queue.empty():
                try:
                    self._frame_queue.get_nowait()
                except queue.Empty:
                    break
            
            # Clear pre-event frames to free memory
            self._pre_event_frames.clear()
            
            # Reset thread reference
            self._recording_thread = None
        
        # Check file size and delete if too small or corrupted
        if output_path and output_path.exists():
            try:
                from evileye.video_recorder.utils import check_and_delete_small_files
                validate_integrity = getattr(self.params, 'validate_video_integrity', True)
                validation_timeout = getattr(self.params, 'video_validation_timeout', 2.0)
                
                # Check file size before deletion to determine reason
                try:
                    stat = output_path.stat()
                    file_size_kb = stat.st_size / 1024.0
                    was_large_enough = file_size_kb >= self.params.min_file_size_kb
                except Exception:
                    was_large_enough = False
                
                deleted = check_and_delete_small_files(
                    output_path, 
                    self.params.min_file_size_kb, 
                    min_age_seconds=0,
                    validate_integrity=validate_integrity,
                    validation_timeout=validation_timeout
                )
                if deleted:
                    # Determine reason for deletion
                    if was_large_enough:
                        reason = "corrupted/invalid video file"
                    else:
                        reason = f"size < {self.params.min_file_size_kb} KB"
                    self.logger.info(f"Deleted event recording: {output_path} ({reason})")
                    return None
            except Exception as e:
                self.logger.debug(f"Error checking file size/integrity: {e}")
            
            self.logger.info(f"Event recording completed: event_id={self._event_id}, "
                           f"event_name={self._event_name}, post_frames={self._post_event_frame_count}, "
                           f"output={output_path}")
            return output_path
        
        return None
    
    def is_recording(self) -> bool:
        """Check if currently recording an event."""
        with self._lock:
            return self._is_recording
    
    def get_event_info(self) -> Optional[dict]:
        """Get current event recording info."""
        with self._lock:
            if not self._is_recording:
                return None
            return {
                "event_id": self._event_id,
                "event_name": self._event_name,
                "event_start_time": self._event_start_time,
                "pre_frames": len(self._pre_event_frames),
                "post_frames": self._post_event_frame_count,
                "output_path": str(self._current_file_path) if self._current_file_path else None
            }
