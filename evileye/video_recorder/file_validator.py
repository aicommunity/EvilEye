"""
File validation utilities for video recorder module.
"""

import re
import time
from pathlib import Path
from typing import Optional

import cv2

from evileye.video_recorder.constants import RecorderConstants

_SPLITMUX_INDEX = re.compile(r"_\d{5}\.(mp4|mkv)$", re.IGNORECASE)


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

            # splitmuxsink parts (`_*00000.mp4`): never integrity-delete.
            # Open fragments have no playable index yet; substring "moov" inside
            # mdat is a false positive that previously made OpenCV mark them
            # corrupt and unlink hundreds of MB mid-write (archive holes).
            if _SPLITMUX_INDEX.search(file_path.name):
                return False, None

            if validate_integrity and file_age >= min_age_seconds:
                if not FileValidator.is_file_valid(file_path, validation_timeout):
                    return True, "corrupted/invalid video file"
        except Exception:
            pass

        return False, None


def _file_contains_moov(file_path: Path) -> bool:
    """Return True only when an ISO BMFF ``moov`` box header is present."""
    try:
        size = file_path.stat().st_size
    except OSError:
        return False
    if size < 12:
        return False
    try:
        with file_path.open("rb") as handle:
            # Fast-start: moov near the beginning. Finalized splitmux: moov near EOF.
            if _scan_region_for_moov_box(handle, 0, min(size, 4 * 1024 * 1024)):
                return True
            tail = min(size, 1024 * 1024)
            if size > tail and _scan_region_for_moov_box(handle, size - tail, tail):
                return True
    except OSError:
        return False
    return False


def _scan_region_for_moov_box(handle, start: int, length: int) -> bool:
    """Look for a plausible ``moov`` box type field, not a raw ``b'moov'`` substring."""
    if length < 8:
        return False
    handle.seek(start)
    data = handle.read(length)
    needle = b"moov"
    idx = 0
    while True:
        found = data.find(needle, idx)
        if found < 0:
            return False
        # ISO box type sits at offset +4 from the size field.
        type_at = found
        size_at = type_at - 4
        if size_at >= 0:
            box_size = int.from_bytes(data[size_at:size_at + 4], "big")
            # Reject accidental media bytes: real moov boxes are reasonably sized.
            if 8 <= box_size <= max(length - size_at, 8) or box_size == 1:
                return True
        idx = found + 1
