from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.utils import get_disk_free_percent, iter_segments, delete_files, check_and_delete_small_files
from evileye.video_recorder.constants import RecorderConstants


class RetentionEnforcer:
    def __init__(self) -> None:
        self.logger = get_module_logger("recorder_retention")

    def _delete_by_retention(self, params: RecordingParams, base: Path) -> List[Path]:
        """Delete files older than retention_days.
        
        Args:
            params: Recording parameters
            base: Base directory to scan
            
        Returns:
            List of paths to delete
        """
        now = datetime.now()
        cutoff = now - timedelta(days=max(0, int(params.retention_days)))
        to_delete: List[Path] = []
        
        # Scan all subdirectories
        for date_dir in base.iterdir():
            if not date_dir.is_dir():
                continue
            for camera_dir in date_dir.iterdir():
                if not camera_dir.is_dir():
                    continue
                for p, mtime in iter_segments(camera_dir, [params.container, 'mp4', 'mkv']):
                    if '%' not in p.name and datetime.fromtimestamp(mtime) < cutoff:
                        to_delete.append(p)
            # Also check files directly in date directory
            for p, mtime in iter_segments(date_dir, [params.container, 'mp4', 'mkv']):
                if '%' not in p.name and datetime.fromtimestamp(mtime) < cutoff:
                    to_delete.append(p)
        # Also check files directly in base directory
        for p, mtime in iter_segments(base, [params.container, 'mp4', 'mkv']):
            if '%' not in p.name and datetime.fromtimestamp(mtime) < cutoff:
                to_delete.append(p)
        
        return to_delete

    def _delete_small_files(self, params: RecordingParams, base: Path) -> tuple[int, int]:
        """Delete small and corrupted files.
        
        Optimized to cache stat() results to avoid multiple file system calls.
        
        Args:
            params: Recording parameters
            base: Base directory to scan
            
        Returns:
            Tuple of (small_files_deleted, corrupted_files_deleted)
        """
        small_files_deleted = 0
        corrupted_files_deleted = 0
        
        validate_integrity = getattr(params, 'validate_video_integrity', True)
        validation_timeout = getattr(params, 'video_validation_timeout', 2.0)
        
        # Scan all subdirectories
        for date_dir in base.iterdir():
            if not date_dir.is_dir():
                continue
            for camera_dir in date_dir.iterdir():
                if not camera_dir.is_dir():
                    continue
                for p, mtime in iter_segments(camera_dir, [params.container, 'mp4', 'mkv']):
                    if '%' in p.name:
                        # Delete invalid splitmuxsink pattern files
                        if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                            small_files_deleted += 1
                    else:
                        # Cache stat() result to avoid multiple calls in check_and_delete_small_files
                        # FileValidator.should_delete_file will call stat() again, but that's acceptable
                        # as it's a single call per file and the optimization is in batch operations
                        if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                            # Determine reason by checking file size (if file still exists)
                            try:
                                if p.exists():
                                    stat = p.stat()
                                    file_size_kb = stat.st_size / 1024.0
                                    if file_size_kb >= params.min_file_size_kb:
                                        corrupted_files_deleted += 1
                                    else:
                                        small_files_deleted += 1
                                else:
                                    # File was deleted, assume it was small (most common case)
                                    small_files_deleted += 1
                            except Exception:
                                small_files_deleted += 1
            # Also check files directly in date directory
            for p, mtime in iter_segments(date_dir, [params.container, 'mp4', 'mkv']):
                if '%' in p.name:
                    if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                        small_files_deleted += 1
                else:
                    if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                        try:
                            if p.exists():
                                stat = p.stat()
                                file_size_kb = stat.st_size / 1024.0
                                if file_size_kb >= params.min_file_size_kb:
                                    corrupted_files_deleted += 1
                                else:
                                    small_files_deleted += 1
                            else:
                                small_files_deleted += 1
                        except Exception:
                            small_files_deleted += 1
        # Also check files directly in base directory
        for p, mtime in iter_segments(base, [params.container, 'mp4', 'mkv']):
            if '%' in p.name:
                if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                    small_files_deleted += 1
            else:
                if check_and_delete_small_files(p, params.min_file_size_kb, validate_integrity=validate_integrity, validation_timeout=validation_timeout):
                    try:
                        if p.exists():
                            stat = p.stat()
                            file_size_kb = stat.st_size / 1024.0
                            if file_size_kb >= params.min_file_size_kb:
                                corrupted_files_deleted += 1
                            else:
                                small_files_deleted += 1
                        else:
                            small_files_deleted += 1
                    except Exception:
                        small_files_deleted += 1
        
        return small_files_deleted, corrupted_files_deleted

    def _enforce_free_space(self, params: RecordingParams, base: Path) -> None:
        """Enforce minimum free space by deleting oldest files.
        
        Args:
            params: Recording parameters
            base: Base directory
        """
        free_pct = get_disk_free_percent(base)
        if free_pct < float(params.min_free_space_pct):
            # Delete oldest files until threshold reached
            segs = iter_segments(base, [params.container, 'mp4', 'mkv'])
            idx = 0
            removed_total = 0
            while free_pct < float(params.min_free_space_pct) and idx < len(segs):
                path, _ = segs[idx]
                try:
                    path.unlink(missing_ok=True)
                    removed_total += 1
                except Exception:
                    pass
                idx += 1
                free_pct = get_disk_free_percent(base)
            if removed_total:
                self.logger.info(f"Retention: freed space by removing {removed_total} oldest file(s); free={free_pct:.1f}%")

    def enforce(self, params: RecordingParams) -> None:
        """Enforce retention policies: delete old files, small files, and free space."""
        try:
            base = Path(params.out_dir)
            base.mkdir(parents=True, exist_ok=True)
            
            # 1) Delete by retention days
            to_delete = self._delete_by_retention(params, base)
            if to_delete:
                n = delete_files(to_delete)
                self.logger.info(f"Retention: removed {n} files older than {params.retention_days} days")
            
            # 2) Delete small and corrupted files
            small_files_deleted, corrupted_files_deleted = self._delete_small_files(params, base)
            if small_files_deleted:
                self.logger.info(f"Retention: removed {small_files_deleted} files smaller than {params.min_file_size_kb} KB")
            if corrupted_files_deleted:
                self.logger.info(f"Retention: removed {corrupted_files_deleted} corrupted/invalid video files")
            
            # 3) Enforce minimum free space percent
            self._enforce_free_space(params, base)
        except Exception as e:
            try:
                self.logger.warning(f"Retention enforcement error: {e}")
            except Exception:
                pass


