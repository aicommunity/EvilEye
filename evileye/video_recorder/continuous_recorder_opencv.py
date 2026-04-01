from __future__ import annotations

from pathlib import Path
from typing import Optional
import threading
import time
from queue import Queue, Empty

import cv2
import numpy as np

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta
from evileye.video_recorder.path_generator import PathGenerator
from evileye.video_recorder.recording_params import RecordingParams


class OpenCVContinuousRecorder(VideoRecorderBase):
    def __init__(self) -> None:
        super().__init__()
        self.logger = get_module_logger("opencv_continuous_recorder")
        self._writer: Optional[cv2.VideoWriter] = None
        self._lock = threading.RLock()
        self._segment_start_ts: float = 0.0
        self._seq: int = 0
        self._frame_size: Optional[tuple[int, int]] = None
        self._fps: float = 25.0
        self._current_file_path: Optional[Path] = None
        self._frames_written: int = 0
        self._frames_last_log_ts: float = 0.0
        self._segments_opened: int = 0
        self._segments_closed: int = 0
        self._frame_queue: Queue[np.ndarray] = Queue(maxsize=8)
        self._writer_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._dropped_frames: int = 0

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        self.source = source_meta
        self.params = params
        self.is_running = bool(params.enabled and params.continuous_recording_enabled)
        if not self.is_running:
            return

        try:
            if source_meta.fps and source_meta.fps > 0:
                self._fps = float(source_meta.fps)
            else:
                self._fps = 25.0
        except Exception:
            self._fps = 25.0

        self._segment_start_ts = 0.0
        self._seq = 0
        self._frame_size = None
        self._current_file_path = None
        self._frames_written = 0
        self._segments_opened = 0
        self._segments_closed = 0
        self._frames_last_log_ts = time.time()
        self._dropped_frames = 0
        self._stop_event.clear()
        self._start_writer_thread()

        self.logger.info(
            "OpenCVContinuousRecorder started for %s (fps=%.2f, segment=%ss, out_dir=%s)",
            source_meta.source_name,
            self._fps,
            self.params.segment_length_sec,
            self.params.out_dir,
        )

    def _need_rotate(self, now: float) -> bool:
        return bool(
            self._segment_start_ts
            and (now - self._segment_start_ts) >= float(self.params.segment_length_sec)
        )

    def _open_new_segment(self, frame: np.ndarray, now: float) -> None:
        self._segment_start_ts = now
        self._seq += 1

        h, w = frame.shape[:2]
        self._frame_size = (w, h)
        path = Path(PathGenerator.generate_stream_path(self.source, self.params, now, self._seq))

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(str(path), fourcc, self._fps, self._frame_size)
        if not writer or not writer.isOpened():
            self.logger.error("Failed to open VideoWriter for %s", path)
            try:
                if writer:
                    writer.release()
            except Exception:
                pass
            self._writer = None
            self._current_file_path = None
            return

        self._writer = writer
        self._current_file_path = path
        self._segments_opened += 1
        self.logger.info("Opened continuous recording segment: %s", path)

    def on_frame(self, frame) -> None:
        if not self.is_running or frame is None:
            return
        if not isinstance(frame, np.ndarray):
            return

        try:
            frame_for_write = frame.copy()
        except Exception:
            frame_for_write = frame
        try:
            if self._frame_queue.full():
                try:
                    self._frame_queue.get_nowait()
                    self._dropped_frames += 1
                except Exception:
                    pass
            self._frame_queue.put_nowait(frame_for_write)
        except Exception:
            self._dropped_frames += 1

    def _start_writer_thread(self) -> None:
        if self._writer_thread is not None and self._writer_thread.is_alive():
            return
        self._writer_thread = threading.Thread(target=self._writer_loop, name="OpenCVContinuousRecorder", daemon=True)
        self._writer_thread.start()

    def _writer_loop(self) -> None:
        while not self._stop_event.is_set() or not self._frame_queue.empty():
            try:
                frame = self._frame_queue.get(timeout=0.2)
            except Empty:
                continue

            now = time.time()
            with self._lock:
                if self._writer is None or self._need_rotate(now):
                    if self._writer is not None:
                        self.rotate_segment()
                    self._open_new_segment(frame, now)

                writer = self._writer
                if writer is None:
                    continue

                try:
                    h, w = frame.shape[:2]
                except Exception:
                    continue

                if self._frame_size is None:
                    self._frame_size = (w, h)

                try:
                    if (w, h) != self._frame_size:
                        frame = cv2.resize(frame, self._frame_size)
                except Exception as e:
                    self.logger.debug("Failed to resize frame for recording: %s", e)
                    continue

                try:
                    writer.write(frame)
                    self._frames_written += 1
                except Exception as e:
                    self.logger.error(
                        "Error writing frame to continuous recorder: %s", e, exc_info=True
                    )
                    continue

                # Lightweight periodic perf log
                try:
                    now2 = time.time()
                    if (now2 - self._frames_last_log_ts) >= 5.0:
                        self._frames_last_log_ts = now2
                        self.logger.debug(
                            "OpenCVContinuousRecorder stats: src=%s fps=%.2f frames_written=%s segments_opened=%s segments_closed=%s queue=%s dropped=%s current=%s",
                            self.source.source_name if self.source else "source",
                            self._fps,
                            self._frames_written,
                            self._segments_opened,
                            self._segments_closed,
                            self._frame_queue.qsize(),
                            self._dropped_frames,
                            str(self._current_file_path) if self._current_file_path else "n/a",
                        )
                except Exception:
                    pass

    def rotate_segment(self) -> None:
        with self._lock:
            writer = self._writer
            path = self._current_file_path
            self._writer = None
            self._current_file_path = None

        if writer is not None:
            self._release_writer_safe(writer, self.logger)
            self._segments_closed += 1
            self._validate_and_delete_small_file(
                path,
                min_size_kb=self.params.min_file_size_kb,
                logger=self.logger,
                validate_integrity=self.params.validate_video_integrity,
                validation_timeout=self.params.video_validation_timeout,
            )

    def stop(self) -> None:
        with self._lock:
            running = self.is_running
            self.is_running = False
            self._stop_event.set()

        if not running:
            return

        if self._writer_thread is not None and self._writer_thread.is_alive():
            self._writer_thread.join(timeout=2.0)

        self.rotate_segment()
        self.logger.info(
            "OpenCVContinuousRecorder stopped for %s (frames_written=%s dropped=%s)",
            self.source.source_name if self.source else "source",
            self._frames_written,
            self._dropped_frames,
        )

