from __future__ import annotations

import os
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from evileye.core.logger import get_module_logger
from evileye.video_recorder.utils import get_disk_free_percent


class StorageMonitor:
    """
    Monitors and manages storage space for the image_dir directory.
    
    Performs periodic checks for:
    - Directory size limits
    - Free disk space limits
    - File retention periods for different data types
    
    Deletes old files in priority order when constraints are violated.
    """
    
    def __init__(self, image_dir: str, config: Optional[Dict] = None):
        """
        Initialize storage monitor.
        
        Args:
            image_dir: Base directory to monitor (e.g., 'EvilEyeData')
            config: Configuration dictionary with monitoring settings
        """
        self.logger = get_module_logger("storage_monitor")
        self.image_dir = Path(image_dir)
        
        # Default configuration
        default_config = {
            "enabled": True,
            "check_interval_seconds": 300,
            "max_dir_size_gb": 200,
            "min_free_space_percent": 10,
            "retention_days": {
                "streaming_video": 7,
                "event_videos": 7,
                "object_images": 180,
                "event_images": 180
            },
            "active_file_age_seconds": 60
        }
        
        # Merge with provided config
        if config:
            default_config.update(config)
            if "retention_days" in config:
                default_config["retention_days"].update(config["retention_days"])
        
        self.enabled = default_config.get("enabled", True)
        self.check_interval_seconds = default_config.get("check_interval_seconds", 300)
        self.max_dir_size_gb = default_config.get("max_dir_size_gb", 200)
        self.min_free_space_percent = default_config.get("min_free_space_percent", 10)
        self.retention_days = default_config.get("retention_days", {})
        self.active_file_age_seconds = default_config.get("active_file_age_seconds", 60)
        
        # Threading
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False
        
        self.logger.info(f"StorageMonitor initialized for directory: {self.image_dir}")
        self.logger.info(f"Enabled: {self.enabled}, Check interval: {self.check_interval_seconds}s")
        self.logger.info(f"Max dir size: {self.max_dir_size_gb} GB, Min free space: {self.min_free_space_percent}%")
    
    def start(self) -> None:
        """Start monitoring thread."""
        if not self.enabled:
            self.logger.info("Storage monitoring is disabled")
            return
        
        if self._running:
            self.logger.warning("Storage monitor is already running")
            return
        
        self._stop_event.clear()
        self._running = True
        
        # Start monitoring thread for periodic checks
        # The thread will perform initial check immediately, then continue with periodic checks
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True, name="StorageMonitor")
        self._monitor_thread.start()
        self.logger.info("Storage monitor started (initial check will run in background thread)")
    
    def stop(self) -> None:
        """Stop monitoring thread."""
        if not self._running:
            return
        
        self.logger.info("Stopping storage monitor...")
        self._stop_event.set()
        self._running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5.0)
            if self._monitor_thread.is_alive():
                self.logger.warning("Storage monitor thread did not stop in time")
            else:
                self.logger.info("Storage monitor stopped")
    
    def _monitor_loop(self) -> None:
        """
        Main monitoring loop running in separate thread.
        
        Performs initial check immediately on startup, then continues with periodic checks.
        All checks run in the same background thread.
        """
        # Perform initial check immediately on startup (in the same background thread)
        self.logger.info("Performing initial storage check and cleanup on startup...")
        self._perform_storage_check(is_initial=True)
        self.logger.info("Initial storage check completed, starting periodic monitoring")
        
        # Continue with periodic checks in the same thread
        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    break
                
                # Perform periodic check
                self._perform_storage_check(is_initial=False)
                
            except Exception as e:
                self.logger.error(f"Error in storage monitor loop: {e}", exc_info=True)
            
            # Wait for next check or stop signal
            if self._stop_event.wait(timeout=self.check_interval_seconds):
                break
    
    def _perform_storage_check(self, is_initial: bool = False) -> None:
        """
        Perform storage check and cleanup.
        
        This method is called both for initial check on startup and for periodic checks.
        All checks run in the same background thread.
        
        Args:
            is_initial: True if this is the initial check on startup, False for periodic checks
        """
        try:
            if not self.enabled:
                return
            
            # Check retention first (has priority - files older than retention period 
            # are deleted regardless of size/space constraints)
            self._check_retention()
            
            # Then check constraints (size and free space limits)
            self._check_constraints()
            
        except Exception as e:
            check_type = "initial" if is_initial else "periodic"
            self.logger.error(f"Error during {check_type} storage check: {e}", exc_info=True)
    
    def _check_constraints(self) -> None:
        """Check general constraints (directory size and free disk space)."""
        try:
            if not self.image_dir.exists():
                self.logger.debug(f"Image directory does not exist: {self.image_dir}")
                return
            
            # Check directory size
            dir_size_gb = self._get_dir_size(self.image_dir) / (1024 ** 3)
            size_violated = dir_size_gb > self.max_dir_size_gb
            
            # Check free disk space
            free_space_percent = get_disk_free_percent(self.image_dir)
            space_violated = free_space_percent < self.min_free_space_percent
            
            if size_violated or space_violated:
                self.logger.warning(
                    f"Storage constraints violated: dir_size={dir_size_gb:.2f} GB "
                    f"(limit={self.max_dir_size_gb} GB), free_space={free_space_percent:.1f}% "
                    f"(limit={self.min_free_space_percent}%)"
                )
                self._delete_old_files_by_priority(size_violated, space_violated)
            else:
                self.logger.debug(
                    f"Storage constraints OK: dir_size={dir_size_gb:.2f} GB, "
                    f"free_space={free_space_percent:.1f}%"
                )
        
        except Exception as e:
            self.logger.error(f"Error checking storage constraints: {e}", exc_info=True)
    
    def _check_retention(self) -> None:
        """
        Check file retention periods for different data types.
        
        This has priority over size/space constraints - files older than retention period
        are deleted regardless of whether storage limits are violated.
        """
        try:
            if not self.image_dir.exists():
                return
            
            now = datetime.now()
            self.logger.debug("Checking file retention periods (priority check)")
            
            # Check streaming video retention
            streaming_retention = self.retention_days.get("streaming_video", 7)
            if streaming_retention > 0:
                self._delete_old_files_by_retention(
                    self.image_dir / "Streams",
                    streaming_retention,
                    now,
                    "streaming video"
                )
            
            # Check event videos retention
            event_videos_retention = self.retention_days.get("event_videos", 7)
            if event_videos_retention > 0:
                events_dir = self.image_dir / "Events"
                if events_dir.exists():
                    for date_dir in events_dir.iterdir():
                        if date_dir.is_dir():
                            videos_dir = date_dir / "Videos"
                            if videos_dir.exists():
                                self._delete_old_files_by_retention(
                                    videos_dir,
                                    event_videos_retention,
                                    now,
                                    "event videos"
                                )
            
            # Check object images retention
            object_images_retention = self.retention_days.get("object_images", 180)
            if object_images_retention > 0:
                self._delete_old_files_by_retention(
                    self.image_dir / "Detections",
                    object_images_retention,
                    now,
                    "object images"
                )
            
            # Check event images retention
            event_images_retention = self.retention_days.get("event_images", 180)
            if event_images_retention > 0:
                events_dir = self.image_dir / "Events"
                if events_dir.exists():
                    for date_dir in events_dir.iterdir():
                        if date_dir.is_dir():
                            images_dir = date_dir / "Images"
                            if images_dir.exists():
                                self._delete_old_files_by_retention(
                                    images_dir,
                                    event_images_retention,
                                    now,
                                    "event images"
                                )
        
        except Exception as e:
            self.logger.error(f"Error checking file retention: {e}", exc_info=True)
    
    def _delete_old_files_by_priority(
        self,
        size_violated: bool,
        space_violated: bool
    ) -> None:
        """
        Delete old files in priority order when constraints are violated.
        
        Priority order:
        1. Streaming video (Streams/)
        2. Event videos (Events/*/Videos/)
        3. Object images (Detections/)
        4. Event images (Events/*/Images/)
        """
        if not (size_violated or space_violated):
            return
        
        self.logger.info(
            f"Starting cleanup due to constraints violation: "
            f"size_violated={size_violated}, space_violated={space_violated}"
        )
        
        deleted_count = 0
        deleted_size = 0
        
        # Priority 1: Streaming video
        streams_dir = self.image_dir / "Streams"
        if streams_dir.exists():
            self.logger.debug(f"Checking streaming video directory: {streams_dir}")
            count, size = self._delete_oldest_files(streams_dir, check_constraints=True)
            deleted_count += count
            deleted_size += size
            if count > 0:
                self.logger.info(f"Deleted {count} streaming video files ({size / (1024**2):.2f} MB)")
            else:
                self.logger.debug(f"No streaming video files deleted from {streams_dir}")
        
        # Check if constraints are still violated
        if not self._constraints_still_violated():
            return
        
        # Priority 2: Event videos
        events_dir = self.image_dir / "Events"
        if events_dir.exists():
            for date_dir in events_dir.iterdir():
                if date_dir.is_dir():
                    videos_dir = date_dir / "Videos"
                    if videos_dir.exists():
                        count, size = self._delete_oldest_files(videos_dir, check_constraints=True)
                        deleted_count += count
                        deleted_size += size
                        if count > 0:
                            self.logger.info(f"Deleted {count} event video files ({size / (1024**2):.2f} MB)")
                        
                        if not self._constraints_still_violated():
                            return
        
        # Priority 3: Object images
        detections_dir = self.image_dir / "Detections"
        if detections_dir.exists():
            count, size = self._delete_oldest_files(detections_dir, check_constraints=True)
            deleted_count += count
            deleted_size += size
            if count > 0:
                self.logger.info(f"Deleted {count} object image files ({size / (1024**2):.2f} MB)")
            
            if not self._constraints_still_violated():
                return
        
        # Priority 4: Event images
        if events_dir.exists():
            for date_dir in events_dir.iterdir():
                if date_dir.is_dir():
                    images_dir = date_dir / "Images"
                    if images_dir.exists():
                        count, size = self._delete_oldest_files(images_dir, check_constraints=True)
                        deleted_count += count
                        deleted_size += size
                        if count > 0:
                            self.logger.info(f"Deleted {count} event image files ({size / (1024**2):.2f} MB)")
                        
                        if not self._constraints_still_violated():
                            return
        
        if deleted_count > 0:
            self.logger.info(
                f"Total cleanup: {deleted_count} files deleted, "
                f"{deleted_size / (1024**3):.2f} GB freed"
            )
            # Remove empty directories after file deletion
            self._remove_empty_directories(self.image_dir)
        else:
            self.logger.warning(
                "Storage constraints violated but no files could be deleted. "
                "All files may be currently being written. Consider disabling recording "
                "or adjusting storage limits."
            )
    
    def _delete_old_files_by_retention(
        self,
        base_dir: Path,
        retention_days: int,
        now: datetime,
        data_type: str
    ) -> None:
        """
        Delete files older than retention period.
        
        This has priority over size/space constraints - files are deleted
        if they exceed retention period, regardless of storage limits.
        """
        if not base_dir.exists() or retention_days <= 0:
            return
        
        cutoff_date = now - timedelta(days=retention_days)
        deleted_count = 0
        deleted_size = 0
        active_files_count = 0
        
        self.logger.debug(
            f"Checking retention for {data_type} in {base_dir}: "
            f"cutoff date = {cutoff_date.strftime('%Y-%m-%d')} ({retention_days} days ago)"
        )
        
        # Recursively find all files
        files_to_check = list(base_dir.rglob("*"))
        self.logger.debug(f"Found {len([f for f in files_to_check if f.is_file()])} files to check for retention")
        
        for file_path in files_to_check:
            if not file_path.is_file():
                continue
            
            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                file_age_days = (now - file_mtime).days
                
                if file_mtime < cutoff_date:
                    if not self._is_file_active(file_path):
                        file_size = file_path.stat().st_size
                        file_path.unlink(missing_ok=True)
                        deleted_count += 1
                        deleted_size += file_size
                        # Log detailed info at DEBUG level to avoid log flooding
                        self.logger.debug(
                            f"Deleted file (retention priority): {file_path} "
                            f"(size: {file_size / (1024**2):.2f} MB, "
                            f"age: {file_age_days} days, retention: {retention_days} days)"
                        )
                    else:
                        active_files_count += 1
                        if active_files_count <= 3:
                            self.logger.debug(
                                f"Skipping active file (retention): {file_path} "
                                f"(age: {file_age_days} days)"
                            )
            except Exception as e:
                self.logger.debug(f"Error processing file {file_path} for retention: {e}")
        
        if deleted_count > 0:
            self.logger.info(
                f"Retention cleanup ({data_type}): {deleted_count} files deleted "
                f"({deleted_size / (1024**2):.2f} MB), older than {retention_days} days"
            )
            # Remove empty directories after file deletion
            self._remove_empty_directories(base_dir)
        elif active_files_count > 0:
            self.logger.debug(
                f"Retention check ({data_type}): {active_files_count} files older than "
                f"{retention_days} days but currently active (being written)"
            )
    
    def _delete_oldest_files(
        self,
        base_dir: Path,
        check_constraints: bool = False
    ) -> Tuple[int, int]:
        """
        Delete oldest files in directory until constraints are satisfied.
        
        Returns:
            Tuple of (deleted_count, deleted_size_bytes)
        """
        deleted_count = 0
        deleted_size = 0
        
        # Collect all files with modification times
        files_with_mtime: List[Tuple[Path, float, int]] = []
        for file_path in base_dir.rglob("*"):
            if file_path.is_file():
                try:
                    stat = file_path.stat()
                    mtime = stat.st_mtime
                    file_size = stat.st_size
                    files_with_mtime.append((file_path, mtime, file_size))
                except Exception:
                    continue
        
        # Sort by modification time (oldest first)
        files_with_mtime.sort(key=lambda x: x[1])
        
        self.logger.debug(f"Found {len(files_with_mtime)} files in {base_dir}, starting deletion...")
        
        active_files_count = 0
        # Delete oldest files until constraints are satisfied
        # Check constraints every N files to avoid expensive recalculations
        check_interval = max(10, len(files_with_mtime) // 100)  # Check every 1% or at least 10 files
        for idx, (file_path, mtime, file_size) in enumerate(files_with_mtime):
            # Check constraints periodically (not after every file to avoid slow recalculations)
            if check_constraints and idx > 0 and idx % check_interval == 0:
                if not self._constraints_still_violated():
                    self.logger.debug("Constraints satisfied, stopping deletion")
                    break
            
            if not self._is_file_active(file_path):
                try:
                    file_mtime = datetime.fromtimestamp(mtime)
                    file_path.unlink(missing_ok=True)
                    deleted_count += 1
                    deleted_size += file_size
                    # Log detailed info at DEBUG level to avoid log flooding
                    self.logger.debug(
                        f"Deleted file (constraints): {file_path} "
                        f"(size: {file_size / (1024**2):.2f} MB, "
                        f"modified: {file_mtime.strftime('%Y-%m-%d %H:%M:%S')})"
                    )
                except Exception as e:
                    self.logger.error(f"Error deleting file {file_path}: {e}", exc_info=True)
            else:
                active_files_count += 1
                if active_files_count <= 5:  # Log first 5 active files
                    self.logger.debug(f"Skipping active file: {file_path}")
        
        if active_files_count > 5:
            self.logger.warning(
                f"Skipped {active_files_count} active files in {base_dir}. "
                f"Storage constraints may be too strict. Consider disabling recording."
            )
        
        self.logger.debug(
            f"Deletion completed: {deleted_count} deleted, {active_files_count} active files skipped"
        )
        
        return deleted_count, deleted_size
    
    def _is_file_active(self, file_path: Path) -> bool:
        """
        Check if file is currently being written.
        
        A file is considered active if it was modified within
        active_file_age_seconds seconds.
        """
        try:
            if not file_path.exists():
                return False
            
            file_mtime = file_path.stat().st_mtime
            file_age = time.time() - file_mtime
            return file_age < self.active_file_age_seconds
        
        except Exception:
            # If we can't check, assume file is active to be safe
            return True
    
    def _constraints_still_violated(self) -> bool:
        """Check if storage constraints are still violated."""
        try:
            if not self.image_dir.exists():
                return False
            
            # Check directory size
            dir_size_gb = self._get_dir_size(self.image_dir) / (1024 ** 3)
            if dir_size_gb > self.max_dir_size_gb:
                return True
            
            # Check free disk space
            free_space_percent = get_disk_free_percent(self.image_dir)
            if free_space_percent < self.min_free_space_percent:
                return True
            
            return False
        
        except Exception:
            return False
    
    def _get_dir_size(self, directory: Path) -> int:
        """
        Calculate total size of directory recursively.
        
        Returns:
            Size in bytes
        """
        total_size = 0
        try:
            for item in directory.rglob("*"):
                if item.is_file():
                    try:
                        total_size += item.stat().st_size
                    except (OSError, PermissionError):
                        pass
        except Exception as e:
            self.logger.debug(f"Error calculating directory size: {e}")
        
        return total_size
    
    def _remove_empty_directories(self, base_dir: Path) -> None:
        """
        Remove empty directories recursively starting from the deepest level.
        
        Args:
            base_dir: Base directory to start cleanup from (won't be deleted itself)
        """
        if not base_dir.exists() or not base_dir.is_dir():
            return
        
        removed_count = 0
        
        try:
            # Collect all directories, sorted by depth (deepest first)
            all_dirs = []
            for root, dirs, files in os.walk(base_dir, topdown=False):
                # topdown=False means we traverse from deepest to shallowest
                dir_path = Path(root)
                all_dirs.append(dir_path)
            
            # Remove empty directories (deepest first)
            for dir_path in all_dirs:
                # Skip base directory itself
                if dir_path == base_dir:
                    continue
                
                try:
                    # Check if directory is empty
                    if dir_path.exists() and dir_path.is_dir():
                        # Try to list directory contents
                        try:
                            contents = list(dir_path.iterdir())
                            if len(contents) == 0:
                                # Directory is empty, remove it
                                dir_path.rmdir()
                                removed_count += 1
                                self.logger.debug(f"Removed empty directory: {dir_path}")
                        except OSError:
                            # Directory might have been removed already or is not accessible
                            pass
                except Exception as e:
                    self.logger.debug(f"Error removing directory {dir_path}: {e}")
            
            if removed_count > 0:
                self.logger.info(f"Removed {removed_count} empty directories")
        
        except Exception as e:
            self.logger.debug(f"Error during empty directory cleanup: {e}")
