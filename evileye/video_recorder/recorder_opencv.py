from __future__ import annotations

import cv2
import time
import threading
from pathlib import Path
from typing import Optional

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import VideoRecorderBase, SourceMeta
from evileye.video_recorder.utils import check_and_delete_small_files


class OpenCVRecorder(VideoRecorderBase):
    def __init__(self) -> None:
        super().__init__()
        self.logger = get_module_logger("recorder_cv")
        self._writer: Optional[cv2.VideoWriter] = None
        self._seq: int = 0
        self._segment_started_ts: float = 0.0
        self._lock = threading.Lock()
        self._frame_size = (0, 0)
        self._fps = 25.0
        self._current_file_path: Optional[Path] = None

    def _fourcc_candidates(self, container: str) -> list[str]:
        c = container.lower()
        if c == "mp4":
            # Prefer widely available MPEG4; then try H264 variants
            return ["mp4v", "avc1", "H264", "X264"]
        # mkv or others
        return ["XVID", "MJPG", "mp4v", "H264"]

    def _next_path(self) -> str:
        # Daily subfolder YYYY-MM-DD inside out_dir, then camera name subfolder
        date_dir = time.strftime("%Y-%m-%d", time.localtime(self._segment_started_ts))
        
        # Compose camera folder name from all source_names or source_ids
        if self.source and self.source.source_names and len(self.source.source_names) > 0:
            camera_folder = "-".join(self.source.source_names)
        elif self.source and self.source.source_ids and len(self.source.source_ids) > 0:
            camera_folder = "-".join(str(sid) for sid in self.source.source_ids)
        elif self.source:
            camera_folder = self.source.source_name
        else:
            camera_folder = "source"
        
        # Create path: out_dir/YYYY-MM-DD/CameraName/
        base_out_dir = Path(self.params.out_dir) if self.params.out_dir else Path(".")
        out_dir = base_out_dir / date_dir / camera_folder
        out_dir.mkdir(parents=True, exist_ok=True)
        
        ts = time.strftime("%Y%m%d_%H%M%S", time.localtime(self._segment_started_ts))
        source_name = (self.source.source_names[0] if self.source and self.source.source_names else 
                       (self.source.source_name if self.source else "source"))
        name = self.params.filename_tmpl.format(
            source_name=source_name,
            start_time=ts,
            seq=self._seq,
            ext=self.params.container,
        )
        return str(out_dir / name)

    def _open_writer(self) -> None:
        # Try configured container + codecs, then fall back to mkv with common codecs
        tried = []
        containers_to_try = [self.params.container]
        if self.params.container.lower() != "mkv":
            containers_to_try.append("mkv")

        for cont in containers_to_try:
            for fourcc_code in self._fourcc_candidates(cont):
                try:
                    # When container differs, adjust extension used in path
                    orig_container = self.params.container
                    self.params.container = cont
                    path = self._next_path()
                    self.params.container = orig_container  # restore for next iteration

                    cc = cv2.VideoWriter_fourcc(*fourcc_code)
                    self.logger.info(f"Opening VideoWriter path={path} fps={self._fps} size={self._frame_size} fourcc={fourcc_code} container={cont}")
                    writer = cv2.VideoWriter(path, cc, self._fps, self._frame_size)
                    if writer and writer.isOpened():
                        # Commit chosen container and writer
                        self.params.container = cont
                        self._writer = writer
                        self._current_file_path = Path(path)
                        self.logger.info(f"VideoWriter opened successfully fourcc={fourcc_code} container={cont}")
                        return
                    else:
                        tried.append((cont, fourcc_code))
                        if writer:
                            writer.release()
                except Exception as e:
                    tried.append((cont, fourcc_code))
                    continue

        self.logger.error(f"Failed to open VideoWriter after tries: {tried}")
        raise RuntimeError("Failed to open VideoWriter")

    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        self.source = source_meta
        self.params = params
        self._fps = float(source_meta.fps or 25.0)
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
                
                # Release writer and verify it's closed
                try:
                    old_writer.release()
                    # Verify writer is closed
                    if old_writer.isOpened():
                        self.logger.warning("VideoWriter still opened after release(), forcing close")
                        # Try to release again
                        try:
                            old_writer.release()
                        except Exception as e:
                            self.logger.debug(f"Error on second release attempt: {e}")
                except Exception as e:
                    self.logger.error(f"Error releasing VideoWriter: {e}", exc_info=True)
                finally:
                    # Clear references regardless of errors
                    self._writer = None
                    old_writer = None
                    self._current_file_path = None
                
                # Check and delete if file is too small
                if current_path and current_path.exists():
                    if check_and_delete_small_files(current_path, self.params.min_file_size_kb):
                        self.logger.info(f"Deleted small file: {current_path} (size < {self.params.min_file_size_kb} KB)")
                
                # Optional: force garbage collection to free memory immediately
                # This can help with memory leaks in long-running processes
                try:
                    import gc
                    # Only collect if we're in a memory-constrained environment
                    # Uncomment the next line if memory leaks persist
                    # gc.collect()
                except Exception:
                    pass
                
            self._seq += 1
            self._segment_started_ts = time.time()
            # Will reopen on next frame

    def stop(self) -> None:
        with self._lock:
            if self._writer is not None:
                # Check and delete last file if too small
                current_path = self._current_file_path
                old_writer = self._writer
                
                # Release writer and verify it's closed
                try:
                    old_writer.release()
                    # Verify writer is closed
                    if old_writer.isOpened():
                        self.logger.warning("VideoWriter still opened after release() in stop(), forcing close")
                        try:
                            old_writer.release()
                        except Exception as e:
                            self.logger.debug(f"Error on second release attempt in stop(): {e}")
                except Exception as e:
                    self.logger.error(f"Error releasing VideoWriter in stop(): {e}", exc_info=True)
                finally:
                    # Clear references regardless of errors
                    self._writer = None
                    old_writer = None
                    self._current_file_path = None
                
                if current_path and current_path.exists():
                    if check_and_delete_small_files(current_path, self.params.min_file_size_kb):
                        self.logger.info(f"Deleted small file: {current_path} (size < {self.params.min_file_size_kb} KB)")
            self.is_running = False
            self.logger.debug("OpenCV recorder stopped and resources released")


