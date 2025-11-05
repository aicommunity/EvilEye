from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable, List, Tuple


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


def check_and_delete_small_files(file_path: Path, min_size_kb: int, min_age_seconds: int = 30) -> bool:
    """
    Check if file exists and is smaller than min_size_kb, delete if so.
    Also deletes files with %05d pattern in name (invalid splitmuxsink files).
    Does NOT delete files that are currently being written (modified recently).
    
    Args:
        file_path: Path to file to check
        min_size_kb: Minimum file size in KB
        min_age_seconds: Minimum age in seconds before file can be deleted (default 30)
                         Files modified within this time are considered "active" and not deleted
        
    Returns:
        True if file was deleted, False otherwise
    """
    try:
        if not file_path.exists():
            return False
        
        import time
        
        # Delete files with %05d pattern in name (invalid splitmuxsink files)
        # But only if they're old enough (not currently being written)
        if '%' in file_path.name:
            try:
                stat = file_path.stat()
                file_age = time.time() - stat.st_mtime
                # Only delete if file is old enough (not currently being written)
                if file_age >= min_age_seconds:
                    file_path.unlink(missing_ok=True)
                    return True
            except Exception:
                pass
            return False
        
        # Check file size
        stat = file_path.stat()
        file_size_kb = stat.st_size / 1024.0
        file_age = time.time() - stat.st_mtime
        
        # Don't delete if file is currently being written (modified recently)
        if file_age < min_age_seconds:
            return False
        
        # Delete if file is small and old enough
        if file_size_kb < min_size_kb:
            file_path.unlink(missing_ok=True)
            return True
        
        return False
    except Exception:
        return False


