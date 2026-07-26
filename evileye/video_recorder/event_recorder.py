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
from evileye.video_recorder.constants import RecorderConstants
from evileye.video_recorder.path_generator import PathGenerator
from evileye.video_recorder.writer_factory import VideoWriterFactory


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
        self._post_frames_enqueued = 0
        self._post_frames_dropped = 0
        self._post_frames_last_log = time.time()

        # Async recording attributes
        self._recording_thread: Optional[threading.Thread] = None
        # Limit queue size to prevent memory leaks (100 frames should be enough for ~4 seconds at 25fps)
        self._frame_queue: queue.Queue = queue.Queue(maxsize=100)
        self._stop_recording: threading.Event = threading.Event()
        self._last_queue_check_time = time.time()
        self._queue_check_interval = 30.0  # Check queue size every 30 seconds

    def _get_event_output_path(self, event_id: int, event_name: str, event_timestamp: float) -> Path:
        """Generate output path for event recording using PathGenerator.

        Local import ensures availability even if module reload order changes.
        """
        # Fallback import to avoid NameError if module state is stale
        try:
            from evileye.video_recorder.path_generator import PathGenerator as _PG  # type: ignore
        except Exception:
            _PG = PathGenerator

        return _PG.generate_event_path(
            source=self.source,
            params=self.params,
            event_id=event_id,
            event_name=event_name,
            event_timestamp=event_timestamp
        )

    def _open_writer(self, output_path: Path, frame_size: Tuple[int, int]) -> bool:
        """Open video writer for event recording using VideoWriterFactory."""
        writer, codec, container = VideoWriterFactory.create_writer(
            path=output_path,
            fps=self._fps,
            frame_size=frame_size,
            container=self.params.container,
            fallback_container="mkv"
        )

        if writer:
            # Update container if fallback was used
            if container != self.params.container:
                output_path = output_path.with_suffix(f".{container}")
            self._writer = writer
            self._current_file_path = output_path
            self.logger.info(f"Event recorder opened: {output_path} (codec={codec}, fps={self._fps})")
            return True
        else:
            self.logger.error(f"Failed to open event recorder writer for {output_path}")
            return False

    def _write_pre_event_frames(self) -> Optional[float]:
        """Write pre-event frames with proper FPS timing.
        
        Returns:
            Last written timestamp, or None if no frames written
        """
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
            frames_written = 0
            for frame, frame_timestamp in sorted_frames[1:]:
                if self._stop_recording.is_set():
                    break

                # Calculate real time difference between frames
                time_diff = frame_timestamp - last_written_time

                # Calculate how many frames should be written based on time difference
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
            # Explicitly free numpy arrays before clearing list
            for frame, _ in self._pre_event_frames:
                if frame is not None:
                    del frame
            self._pre_event_frames.clear()
        else:
            # No pre-event frames, set last timestamp to event time
            last_written_time = self._event_start_time

        return last_written_time

    def _process_post_event_frames(self, last_written_time: Optional[float]) -> None:
        """Process post-event frames from queue.
        
        Args:
            last_written_time: Timestamp of last written frame (from pre-event frames)
        """
        self.logger.debug("Starting to process post-event frames from queue")
        while not self._stop_recording.is_set():
            try:
                # Periodic queue size monitoring and cleanup
                current_time = time.time()
                if current_time - self._last_queue_check_time >= self._queue_check_interval:
                    queue_size = self._frame_queue.qsize()
                    if queue_size > 80:  # Queue is 80% full
                        self.logger.warning(f"EventRecorder frame queue is {queue_size}/100 full, forcing cleanup")
                        # Remove oldest frames to prevent overflow
                        removed = 0
                        while self._frame_queue.qsize() > 50 and removed < 20:
                            try:
                                old_frame, _ = self._frame_queue.get_nowait()
                                if old_frame is not None:
                                    del old_frame
                                removed += 1
                            except queue.Empty:
                                break
                        if removed > 0:
                            self.logger.info(f"Cleaned up {removed} frames from queue to prevent overflow")
                    self._last_queue_check_time = current_time

                # Get frame from queue with timeout
                frame_data = self._frame_queue.get(timeout=0.1)
                frame, frame_timestamp = frame_data

                # Check if we've exceeded post-event duration
                elapsed_time = frame_timestamp - self._event_start_time
                if elapsed_time >= self.params.event_post_seconds:
                    self.logger.info(
                        f"Post-event duration exceeded: elapsed={elapsed_time:.2f}s, limit={self.params.event_post_seconds}s, stopping recording")
                    break

                # Write frame with proper timing
                if last_written_time is not None:
                    time_diff = frame_timestamp - last_written_time
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

    def _recording_worker(self) -> None:
        """
        Worker function for async recording thread.
        Writes pre-event frames with proper timing, then processes post-event frames from queue.
        """
        try:
            # Write pre-event frames
            last_written_time = self._write_pre_event_frames()

            # Process post-event frames
            self._process_post_event_frames(last_written_time)

        except Exception as e:
            self.logger.error(f"Error in recording worker: {e}", exc_info=True)
        finally:
            self.logger.debug("Recording worker finished")

    def _prepare_recording(self, event_id: int, event_timestamp: float) -> bool:
        """Prepare recording by getting pre-event frames and determining timestamp type.
        
        Args:
            event_id: Event ID
            event_timestamp: Event timestamp
            
        Returns:
            True if preparation successful, False otherwise
        """
        # Get pre-event frames from buffer
        self._pre_event_frames = self.event_buffer.get_frames_before(
            event_timestamp,
            self.params.event_pre_seconds
        )

        if not self._pre_event_frames:
            buffer_size = self.event_buffer.size() if self.event_buffer else 0
            buffer_duration = self.event_buffer.get_duration() if self.event_buffer else 0.0
            self.logger.warning(
                f"No pre-event frames found for event {event_id}, recording anyway "
                f"(EventBuffer: size={buffer_size}, duration={buffer_duration:.1f}s)"
            )

        # Determine timestamp type (relative vs absolute)
        if self._pre_event_frames:
            first_frame_ts = self._pre_event_frames[0][1]
            last_frame_ts = self._pre_event_frames[-1][1]

            if first_frame_ts < RecorderConstants.TIMESTAMP_THRESHOLD_ABSOLUTE:
                # Video file: use relative timestamps
                self._event_start_time = last_frame_ts + self._frame_interval
                self.logger.debug(
                    f"Using relative timestamps for video file: event_start_time={self._event_start_time:.3f}s")
            else:
                # Live source: use absolute timestamps
                self._event_start_time = event_timestamp
                self.logger.debug(
                    f"Using absolute timestamps for live source: event_start_time={self._event_start_time:.3f}s")
        else:
            # No pre-event frames, use event_timestamp as-is
            self._event_start_time = event_timestamp

        return True

    def _determine_frame_size(self, event_id: int) -> Tuple[int, int]:
        """Determine frame size from available sources.
        
        Args:
            event_id: Event ID for logging
            
        Returns:
            Frame size as (width, height)
        """
        frame_size = None

        if self._pre_event_frames:
            h, w = self._pre_event_frames[0][0].shape[:2]
            frame_size = (w, h)
        elif self.source.width and self.source.height:
            frame_size = (int(self.source.width), int(self.source.height))
        else:
            # Try to get frame size from buffer
            try:
                with self.event_buffer.lock:
                    if len(self.event_buffer.buffer) > 0:
                        any_frame, _ = self.event_buffer.buffer[-1]
                        h, w = any_frame.shape[:2]
                        frame_size = (w, h)
                        self.logger.debug(f"Using frame size from buffer: {frame_size}")
            except Exception as e:
                self.logger.debug(f"Could not get frame size from buffer: {e}")

        if frame_size is None:
            self.logger.warning(f"Cannot determine frame size for event {event_id}, using default")
            frame_size = (1920, 1080)  # Default fallback

        return frame_size

    def _calculate_relative_path(self, output_path: Path) -> str:
        """Calculate relative path from absolute path.
        
        Args:
            output_path: Absolute output path
            
        Returns:
            Relative path string
        """
        try:
            path_parts = output_path.parts
            if 'Events' in path_parts:
                events_idx = path_parts.index('Events')
                relative_parts = path_parts[events_idx:]
                return str(Path(*relative_parts))
            else:
                self.logger.warning(f"Could not determine relative path for video: {output_path}")
                return str(output_path)
        except Exception as e:
            self.logger.warning(f"Error calculating relative video path: {e}")
            return str(output_path)

    def _initialize_writer(self, output_path: Path, frame_size: Tuple[int, int]) -> bool:
        """Initialize video writer for event recording.
        
        Args:
            output_path: Output file path
            frame_size: Frame size as (width, height)
            
        Returns:
            True if writer initialized successfully, False otherwise
        """
        return self._open_writer(output_path, frame_size)

    def _start_recording_thread(self, event_id: int) -> None:
        """Start recording worker thread.
        
        Args:
            event_id: Event ID for thread naming
        """
        # Clear queue and reset stop event
        while not self._frame_queue.empty():
            try:
                old_frame, _ = self._frame_queue.get_nowait()
                # Explicitly free memory from removed frame
                if old_frame is not None:
                    del old_frame
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

            # Prepare recording (get pre-event frames, determine timestamp type)
            if not self._prepare_recording(event_id, event_timestamp):
                return False, None

            # Determine frame size
            frame_size = self._determine_frame_size(event_id)

            # Generate output path
            output_path = self._get_event_output_path(event_id, event_name, event_timestamp)
            relative_video_path = self._calculate_relative_path(output_path)

            # Initialize writer
            if not self._initialize_writer(output_path, frame_size):
                return False, None

            # Initialize recording state
            self._is_recording = True
            self._event_id = event_id
            self._event_name = event_name
            self._post_event_frame_count = 0

            # Start recording thread
            self._start_recording_thread(event_id)

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
                self.logger.debug(
                    f"Post-event duration exceeded in add_post_event_frame: elapsed={elapsed_time:.2f}s, limit={self.params.event_post_seconds}s")
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
        # IMPORTANT: do not copy every incoming frame. For high FPS sources this can
        # burn CPU and inflate RSS. Queue backpressure + dropping is sufficient.
        try:
            self._frame_queue.put_nowait((frame, timestamp))
            self._post_frames_enqueued += 1
            return True
        except queue.Full:
            self._post_frames_dropped += 1
            # Queue is full - try to remove oldest frame and add new one
            try:
                # Remove oldest frame to make room
                try:
                    old_frame, _ = self._frame_queue.get_nowait()
                    # Explicitly free memory from removed frame
                    if old_frame is not None:
                        del old_frame
                except queue.Empty:
                    pass
                # Try to add new frame again
                try:
                    self._frame_queue.put_nowait((frame, timestamp))
                    self.logger.debug("Frame queue was full, dropped oldest frame and added new one")
                except queue.Full:
                    self.logger.warning("Frame queue is still full after removing oldest frame, dropping new frame")
            except Exception as e:
                self.logger.debug(f"Error handling full queue: {e}")
            return True  # Continue recording, just drop this frame
        finally:
            try:
                now = time.time()
                if (now - self._post_frames_last_log) >= 5.0:
                    self._post_frames_last_log = now
                    qsz = None
                    try:
                        qsz = self._frame_queue.qsize()
                    except Exception:
                        qsz = "n/a"
                    self.logger.debug(
                        "EventRecorder post-frames: enq=%s dropped=%s queue=%s/100",
                        self._post_frames_enqueued,
                        self._post_frames_dropped,
                        qsz,
                    )
            except Exception:
                pass

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
            self._recording_thread.join(timeout=RecorderConstants.RECORDING_THREAD_JOIN_TIMEOUT)
            if self._recording_thread.is_alive():
                self.logger.warning("Recording thread did not finish in time")

        # Close writer safely
        with self._lock:
            output_path = self._current_file_path

            if self._writer:
                # Use safe release pattern (similar to VideoRecorderBase)
                try:
                    self._writer.release()
                    if self._writer.isOpened():
                        self.logger.warning("VideoWriter still opened after release(), forcing close")
                        try:
                            self._writer.release()
                        except Exception as e:
                            self.logger.debug(f"Error on second release attempt: {e}")
                except Exception as e:
                    self.logger.error(f"Error releasing VideoWriter: {e}", exc_info=True)
                finally:
                    self._writer = None

            # Clear queue
            while not self._frame_queue.empty():
                try:
                    old_frame, _ = self._frame_queue.get_nowait()
                    # Explicitly free memory from removed frame
                    if old_frame is not None:
                        del old_frame
                except queue.Empty:
                    break

            # Clear pre-event frames to free memory
            # Explicitly free numpy arrays before clearing list
            for frame, _ in self._pre_event_frames:
                if frame is not None:
                    del frame
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
