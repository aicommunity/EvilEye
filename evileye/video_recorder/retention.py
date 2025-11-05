from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List

from evileye.core.logger import get_module_logger
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.utils import get_disk_free_percent, iter_segments, delete_files, check_and_delete_small_files


class RetentionEnforcer:
    def __init__(self) -> None:
        self.logger = get_module_logger("recorder_retention")

    def enforce(self, params: RecordingParams) -> None:
        try:
            base = Path(params.out_dir)
            base.mkdir(parents=True, exist_ok=True)
            now = datetime.now()
            # 1) Delete by retention days
            cutoff = now - timedelta(days=max(0, int(params.retention_days)))
            to_delete: List[Path] = []
            small_files_deleted = 0
            
            # Recursively scan all subdirectories (date folders and camera folders)
            for date_dir in base.iterdir():
                if not date_dir.is_dir():
                    continue
                for camera_dir in date_dir.iterdir():
                    if not camera_dir.is_dir():
                        continue
                    # Check all video files in camera directory
                    for p, mtime in iter_segments(camera_dir, [params.container, 'mp4', 'mkv']):
                        # Delete files with invalid name pattern (%05d) - invalid splitmuxsink files
                        if '%' in p.name:
                            if check_and_delete_small_files(p, params.min_file_size_kb):
                                small_files_deleted += 1
                        # Delete by retention days
                        elif datetime.fromtimestamp(mtime) < cutoff:
                            to_delete.append(p)
                        # Delete small files (check all files, not just old ones)
                        elif check_and_delete_small_files(p, params.min_file_size_kb):
                            small_files_deleted += 1
                    # Also check files directly in date directory (backward compatibility)
                    for p, mtime in iter_segments(date_dir, [params.container, 'mp4', 'mkv']):
                        # Delete files with invalid name pattern (%05d)
                        if '%' in p.name:
                            if check_and_delete_small_files(p, params.min_file_size_kb):
                                small_files_deleted += 1
                        elif datetime.fromtimestamp(mtime) < cutoff:
                            to_delete.append(p)
                        elif check_and_delete_small_files(p, params.min_file_size_kb):
                            small_files_deleted += 1
                # Also check files directly in base directory (backward compatibility)
                for p, mtime in iter_segments(base, [params.container, 'mp4', 'mkv']):
                    # Delete files with invalid name pattern (%05d)
                    if '%' in p.name:
                        if check_and_delete_small_files(p, params.min_file_size_kb):
                            small_files_deleted += 1
                    elif datetime.fromtimestamp(mtime) < cutoff:
                        to_delete.append(p)
                    elif check_and_delete_small_files(p, params.min_file_size_kb):
                        small_files_deleted += 1
            
            if to_delete:
                n = delete_files(to_delete)
                self.logger.info(f"Retention: removed {n} files older than {params.retention_days} days")
            if small_files_deleted:
                self.logger.info(f"Retention: removed {small_files_deleted} files smaller than {params.min_file_size_kb} KB")

            # 2) Enforce minimum free space percent
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
        except Exception as e:
            try:
                self.logger.warning(f"Retention enforcement error: {e}")
            except Exception:
                pass


