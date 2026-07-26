from __future__ import annotations

import cv2
import time
import threading
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta
from evileye.video_recorder.path_generator import PathGenerator
from evileye.video_recorder.constants import RecorderConstants
from evileye.video_recorder.writer_factory import VideoWriterFactory
from evileye.video_recorder.exceptions import RecorderInitializationError, RecorderWriteError


class OpenCVRecorder(VideoRecorderBase):
    def __init__(self, path_generator: PathGenerator | None = None,
                 writer_factory: VideoWriterFactory | None = None) -> None:
        super().__init__()
        self.logger = get_module_logger("recorder_cv")
        self._writer: Optional[cv2.VideoWriter] = None
        self._seq: int = 0
        self._segment_started_ts: float = 0.0
        self._lock = threading.Lock()
        self._frame_size = (0, 0)
        self._fps = RecorderConstants.DEFAULT_FPS
        self._current_file_path: Optional[Path] = None
        self.path_generator = path_generator or PathGenerator()
        self.writer_factory = writer_factory or VideoWriterFactory()

    def _next_path(self) -> str:
        return self.path_generator.generate_stream_path(
            source=self.source,
            params=self.params,
            segment_started_ts=self._segment_started_ts,
            seq=self._seq,
            use_pattern=False,
        )

    def _open_writer(self) -> None:
        """Open video writer using VideoWriterFactory."""
        path = self._next_path()

        writer, codec, container = self.writer_factory.create_writer(
            path=path,
            fps=self._fps,
            frame_size=self._frame_size,
            container=self.params.container,
            fallback_container="mkv"
        )

        if writer:
            self.params.container = container
            self._writer = writer
            self._current_file_path = Path(path)
            self.logger.info(f"VideoWriter opened successfully codec={codec} container={container}")
        else:
            error_msg = f"Failed to open VideoWriter for path={path}"
            self.logger.error(error_msg)
            raise RecorderInitializationError(error_msg)

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        self.source = source_meta
        self.params = params
        self._fps = float(source_meta.fps or RecorderConstants.DEFAULT_FPS)
        w = int(source_meta.width or 0)
        h = int(source_meta.height or 0)
        if w <= 0 or h <= 0:
            # Defer size until first frame
            self._frame_size = (0, 0)
        else:
            self._frame_size = (w, h)
        self._seq = 0
        self._segment_started_ts = time.time()
        self.is_running = True
        # Open on first frame when size known

    def on_frame(self, frame_bgr) -> None:
        if not self.is_running:
            return
        with self._lock:
            if self._frame_size == (0, 0):
                h, w = frame_bgr.shape[:2]
                self._frame_size = (w, h)
                self._open_writer()
            # Rotate by time if needed
            elapsed = time.time() - self._segment_started_ts
            if elapsed >= self.params.segment_length_sec:
                self.logger.info("Rotate recording segment (time threshold reached)")
                self.rotate_segment()
            if self._writer is None:
                self._open_writer()
            self._writer.write(frame_bgr)

    def rotate_segment(self) -> None:
        with self._lock:
            if self._writer is not None:
                # Get path to current file before closing
                current_path = self._current_file_path
                old_writer = self._writer

                # Release writer safely
                self._release_writer_safe(old_writer, self.logger)

                # Clear references
                self._writer = None
                old_writer = None
                self._current_file_path = None

                # Check and delete if file is too small
                self._validate_and_delete_small_file(
                    current_path,
                    self.params.min_file_size_kb,
                    self.logger
                )

            self._seq += 1
            self._segment_started_ts = time.time()
            # Will reopen on next frame

    def stop(self) -> None:
        with self._lock:
            if self._writer is not None:
                # Check and delete last file if too small
                current_path = self._current_file_path
                old_writer = self._writer

                # Release writer safely
                self._release_writer_safe(old_writer, self.logger)

                # Clear references
                self._writer = None
                old_writer = None
                self._current_file_path = None

                # Validate and delete if too small
                self._validate_and_delete_small_file(
                    current_path,
                    self.params.min_file_size_kb,
                    self.logger
                )
            self.is_running = False
            self.logger.debug("OpenCV recorder stopped and resources released")
