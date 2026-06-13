"""
File validation utilities for video recorder module.
"""

import time
from pathlib import Path
from typing import Optional

import cv2

from evileye.video_recorder.constants import RecorderConstants


class FileValidator:
    @staticmethod
    def is_file_valid(file_path: Path, timeout_seconds: float = 2.0) -> bool:
        try:
            if not file_path.exists():
                return False

            start_time = time.time()
            cap = cv2.VideoCapture(str(file_path))
            if not cap.isOpened():
                return False

            try:
                ret, frame = cap.read()
                if not ret or frame is None:
                    return False

                fps = cap.get(cv2.CAP_PROP_FPS)
                frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
                width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

                if (time.time() - start_time) > timeout_seconds:
                    return False

                if fps == 0 and frame_count == 0 and (width == 0 or height == 0):
                    return False

                return True
            finally:
                cap.release()
        except Exception:
            return False

    @staticmethod
    def should_delete_file(
            file_path: Path,
            min_size_kb: int,
            min_age_seconds: int = RecorderConstants.MIN_FILE_AGE_SECONDS,
            validate_integrity: bool = True,
            validation_timeout: float = 2.0,
    ) -> tuple[bool, Optional[str]]:
        if not file_path.exists():
            return False, None

        if "%" in file_path.name:
            try:
                stat = file_path.stat()
                if (time.time() - stat.st_mtime) >= min_age_seconds:
                    return True, "invalid splitmuxsink pattern"
            except Exception:
                pass
            return False, None

        try:
            stat = file_path.stat()
            file_size_kb = stat.st_size / 1024.0
            file_age = time.time() - stat.st_mtime

            if file_age < min_age_seconds:
                return False, None

            if file_size_kb < min_size_kb:
                return True, f"size < {min_size_kb} KB"

            if validate_integrity and file_age >= min_age_seconds:
                if not FileValidator.is_file_valid(file_path, validation_timeout):
                    return True, "corrupted/invalid video file"
        except Exception:
            pass

        return False, None
