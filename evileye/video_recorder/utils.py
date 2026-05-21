from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Iterable, List, Tuple
from evileye.video_recorder.constants import RecorderConstants
from evileye.video_recorder.file_validator import FileValidator


def get_disk_free_percent(path: str | os.PathLike) -> float:
    p = Path(path)
    try:
        st = os.statvfs(str(p.resolve()))
    except Exception:
        # Fallback to parent directory
        st = os.statvfs(str(p.parent.resolve()))
    total = float(st.f_blocks) * float(st.f_frsize)
    free = float(st.f_bavail) * float(st.f_frsize)
    if total <= 0:
        return 0.0
    return (free / total) * 100.0


def iter_segments(dir_path: str | os.PathLike, exts: Iterable[str]) -> List[Tuple[Path, float]]:
    """List segments (path, mtime) for given extensions in directory."""
    base = Path(dir_path)
    if not base.exists():
        return []
    exts_lower = {e.lower().lstrip('.') for e in exts}
    items: List[Tuple[Path, float]] = []
    for p in base.glob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower().lstrip('.') in exts_lower:
            try:
                items.append((p, p.stat().st_mtime))
            except Exception:
                continue
    items.sort(key=lambda x: x[1])
    return items


def delete_files(paths: List[Path]) -> int:
    removed = 0
    for p in paths:
        try:
            p.unlink(missing_ok=True)
            removed += 1
        except Exception:
            pass
    return removed


def validate_video_file(file_path: Path, timeout_seconds: float = 2.0) -> bool:
    """
    Fast video file integrity check.
    
    Checks:
    - File can be opened
    - First frame can be read
    - Basic metadata is available
    
    Args:
        file_path: Path to video file
        timeout_seconds: Maximum check time (default 2 seconds)
    
    Returns:
        True if file is valid, False if corrupted
    """
    return FileValidator.is_file_valid(file_path, timeout_seconds)


def check_and_delete_small_files(file_path: Path, min_size_kb: int,
                                 min_age_seconds: int = RecorderConstants.MIN_FILE_AGE_SECONDS,
                                 validate_integrity: bool = True, validation_timeout: float = 2.0) -> bool:
    """
    Check if file exists and should be deleted, delete if so.
    
    Uses FileValidator to determine if file should be deleted based on:
    - File size (smaller than min_size_kb)
    - File integrity (corrupted files)
    - Invalid patterns (splitmuxsink patterns)
    
    Does NOT delete files that are currently being written (modified recently).
    
    Args:
        file_path: Path to file to check
        min_size_kb: Minimum file size in KB
        min_age_seconds: Minimum age in seconds before file can be deleted
        validate_integrity: If True, also validate video file integrity
        validation_timeout: Timeout for video validation in seconds
        
    Returns:
        True if file was deleted, False otherwise
    """
    should_delete, reason = FileValidator.should_delete_file(
        file_path,
        min_size_kb,
        min_age_seconds,
        validate_integrity,
        validation_timeout
    )

    if should_delete:
        try:
            file_path.unlink(missing_ok=True)
            return True
        except Exception:
            return False

    return False
