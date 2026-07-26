from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Dict, Any
from pathlib import Path
import cv2

from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.utils import check_and_delete_small_files


@dataclass
class SourceMeta:
    source_name: str
    source_address: Optional[str]
    source_type: Optional[str]
    width: Optional[int] = None
    height: Optional[int] = None
    fps: Optional[float] = None
    username: Optional[str] = None
    password: Optional[str] = None
    source_names: Optional[list[str]] = None  # All source names (for split sources)
    source_ids: Optional[list[int]] = None  # All source IDs (for split sources)


class VideoRecorderBase(ABC):
    """Abstract base for concrete recorders (GStreamer/OpenCV)."""

    def __init__(self) -> None:
        self.params: RecordingParams = RecordingParams()
        self.source: Optional[SourceMeta] = None
        self.is_running: bool = False

    def _release_writer_safe(self, writer: Optional[cv2.VideoWriter], logger) -> None:
        """Safely release video writer with verification.
        
        Args:
            writer: VideoWriter to release
            logger: Logger instance for logging
        """
        if writer is None:
            return

        try:
            writer.release()
            # Verify writer is closed
            if writer.isOpened():
                logger.warning("VideoWriter still opened after release(), forcing close")
                try:
                    writer.release()
                except Exception as e:
                    logger.debug(f"Error on second release attempt: {e}")
        except Exception as e:
            logger.error(f"Error releasing VideoWriter: {e}", exc_info=True)

    def _validate_and_delete_small_file(
            self,
            file_path: Optional[Path],
            min_size_kb: int,
            logger,
            validate_integrity: bool = True,
            validation_timeout: float = 2.0
    ) -> bool:
        """Validate and delete file if too small or corrupted.
        
        Args:
            file_path: Path to file to check
            min_size_kb: Minimum file size in KB
            logger: Logger instance
            validate_integrity: Whether to validate video integrity
            validation_timeout: Timeout for validation
            
        Returns:
            True if file was deleted, False otherwise
        """
        if not file_path or not file_path.exists():
            return False

        try:
            # Check file size before deletion to determine reason
            try:
                stat = file_path.stat()
                file_size_kb = stat.st_size / 1024.0
                was_large_enough = file_size_kb >= min_size_kb
            except Exception:
                was_large_enough = False

            deleted = check_and_delete_small_files(
                file_path,
                min_size_kb,
                min_age_seconds=0,
                validate_integrity=validate_integrity,
                validation_timeout=validation_timeout
            )

            if deleted:
                # Determine reason for deletion
                if was_large_enough:
                    reason = "corrupted/invalid video file"
                else:
                    reason = f"size < {min_size_kb} KB"
                logger.info(f"Deleted file: {file_path} ({reason})")
                return True
        except Exception as e:
            logger.debug(f"Error checking file size/integrity: {e}")

        return False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            self.stop()
        except Exception:
            pass

    @abstractmethod
    def start(self, source_meta: SourceMeta, params: RecordingParams) -> None:
        ...

    @abstractmethod
    def on_frame(self, frame) -> None:
        ...

    @abstractmethod
    def rotate_segment(self) -> None:
        ...

    @abstractmethod
    def stop(self) -> None:
        ...
