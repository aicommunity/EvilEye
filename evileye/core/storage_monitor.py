from __future__ import annotations

import os
import shutil
import time
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Tuple

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
        self.logger = get_module_logger("storage_monitor")
        self.image_dir = Path(image_dir)

        default_config = {
            "enabled": True,
            "check_interval_seconds": 300,
            "max_dir_size_gb": 200,
            "min_free_space_percent": 10,
            "max_cleanup_seconds": 120,
            "max_files_per_cycle": 500,
            "dir_size_cache_ttl_seconds": 60,
            "heartbeat_interval_seconds": 30,
            "initial_delay_seconds": int(
                os.environ.get("EVILEYE_STORAGE_INITIAL_DELAY_SEC", "0")
            ),
            "retention_days": {
                "streaming_video": 7,
                "event_videos": 7,
                "object_images": 180,
                "event_images": 180,
            },
            "active_file_age_seconds": 60,
        }

        if config:
            default_config.update(config)
            if "retention_days" in config:
                default_config["retention_days"].update(config["retention_days"])

        self.enabled = default_config.get("enabled", True)
        self.check_interval_seconds = default_config.get("check_interval_seconds", 300)
        self.max_dir_size_gb = default_config.get("max_dir_size_gb", 200)
        self.min_free_space_percent = default_config.get("min_free_space_percent", 10)
        self.max_cleanup_seconds = float(default_config.get("max_cleanup_seconds", 120))
        self.max_files_per_cycle = int(default_config.get("max_files_per_cycle", 500))
        self.dir_size_cache_ttl_seconds = float(
            default_config.get("dir_size_cache_ttl_seconds", 60)
        )
        self.heartbeat_interval_seconds = float(
            default_config.get("heartbeat_interval_seconds", 30)
        )
        self.initial_delay_seconds = float(default_config.get("initial_delay_seconds", 0))
        self.retention_days = default_config.get("retention_days", {})
        self.active_file_age_seconds = default_config.get("active_file_age_seconds", 60)
        self.stop_timeout_seconds = float(
            os.environ.get("EVILEYE_STORAGE_MONITOR_STOP_TIMEOUT_SEC", "20.0")
        )

        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

        self._dir_size_cache_bytes: Optional[int] = None
        self._dir_size_cache_time: float = 0.0
        self._cleanup_deadline: float = 0.0
        self._files_deleted_this_cycle = 0
        self._last_heartbeat: float = 0.0
        self._newest_streaming_files: Dict[Path, float] = {}

        self.logger.info(f"StorageMonitor initialized for directory: {self.image_dir}")
        self.logger.info(f"Enabled: {self.enabled}, Check interval: {self.check_interval_seconds}s")
        self.logger.info(
            f"Max dir size: {self.max_dir_size_gb} GB, Min free space: {self.min_free_space_percent}%"
        )
        self.logger.info(
            f"Cleanup budget: {self.max_cleanup_seconds}s, max {self.max_files_per_cycle} files/cycle"
        )

    def start(self) -> None:
        if not self.enabled:
            self.logger.info("Storage monitoring is disabled")
            return

        if self._running:
            self.logger.warning("Storage monitor is already running")
            return

        self._stop_event.clear()
        self._running = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop, daemon=True, name="StorageMonitor"
        )
        self._monitor_thread.start()
        self.logger.info("Storage monitor started (initial check will run in background thread)")

    def stop(self) -> None:
        if not self._running:
            return

        self.logger.info("Stopping storage monitor...")
        self._stop_event.set()
        self._running = False

        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=self.stop_timeout_seconds)
            if self._monitor_thread.is_alive():
                self.logger.warning(
                    "Storage monitor thread did not stop in %.1fs timeout",
                    self.stop_timeout_seconds,
                )
            else:
                self.logger.info("Storage monitor stopped")

    def _monitor_loop(self) -> None:
        if self.initial_delay_seconds > 0:
            self.logger.info(
                "Delaying initial storage check for %.0fs to avoid competing with startup",
                self.initial_delay_seconds,
            )
            if self._stop_event.wait(timeout=self.initial_delay_seconds):
                return

        self.logger.info("Performing initial storage check and cleanup on startup...")
        self._begin_cleanup_cycle()
        self._perform_storage_check(is_initial=True)
        if self._stop_event.is_set() or (not self.enabled) or (not self._running):
            return
        self.logger.info("Initial storage check completed, starting periodic monitoring")

        while not self._stop_event.is_set():
            try:
                if not self.enabled:
                    break
                self._begin_cleanup_cycle()
                self._perform_storage_check(is_initial=False)
            except Exception as e:
                self.logger.error(f"Error in storage monitor loop: {e}", exc_info=True)

            if self._stop_event.wait(timeout=self.check_interval_seconds):
                break

    def _begin_cleanup_cycle(self) -> None:
        self._cleanup_deadline = time.time() + self.max_cleanup_seconds
        self._files_deleted_this_cycle = 0
        self._last_heartbeat = time.time()
        self._refresh_newest_streaming_files()

    def _cleanup_budget_exhausted(self) -> bool:
        if self._files_deleted_this_cycle >= self.max_files_per_cycle:
            self.logger.info(
                "Cleanup file budget reached (%s files); will continue next cycle",
                self.max_files_per_cycle,
            )
            return True
        if time.time() >= self._cleanup_deadline:
            self.logger.info(
                "Cleanup time budget reached (%.0fs); will continue next cycle",
                self.max_cleanup_seconds,
            )
            return True
        return False

    def _maybe_heartbeat(self, phase: str) -> None:
        now = time.time()
        if now - self._last_heartbeat >= self.heartbeat_interval_seconds:
            self._last_heartbeat = now
            self.logger.info(
                "Storage cleanup in progress (%s): deleted=%s files this cycle",
                phase,
                self._files_deleted_this_cycle,
            )

    def _perform_storage_check(self, is_initial: bool = False) -> None:
        try:
            if not self.enabled:
                return

            self._check_retention()

            if not is_initial:
                self._check_constraints()

        except Exception as e:
            check_type = "initial" if is_initial else "periodic"
            self.logger.error(f"Error during {check_type} storage check: {e}", exc_info=True)

    def _check_constraints(self) -> None:
        try:
            if not self.image_dir.exists():
                return

            dir_size_gb = self._get_dir_size(self.image_dir, force_refresh=True) / (1024 ** 3)
            free_space_percent = get_disk_free_percent(self.image_dir)
            size_violated = dir_size_gb > self.max_dir_size_gb
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
        try:
            if not self.image_dir.exists():
                return

            now = datetime.now()
            self.logger.debug("Checking file retention periods (priority check)")

            streaming_retention = self.retention_days.get("streaming_video", 7)
            if streaming_retention > 0:
                self._delete_old_files_by_retention(
                    self.image_dir / "Streams",
                    streaming_retention,
                    now,
                    "streaming video",
                )

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
                                    "event videos",
                                )

            object_images_retention = self.retention_days.get("object_images", 180)
            if object_images_retention > 0:
                self._delete_legacy_images_by_date(object_images_retention, now)
                self._delete_old_files_by_retention(
                    self.image_dir / "Detections",
                    object_images_retention,
                    now,
                    "object images",
                )

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
                                    "event images",
                                )

        except Exception as e:
            self.logger.error(f"Error checking file retention: {e}", exc_info=True)

    def _delete_legacy_images_by_date(self, retention_days: int, now: datetime) -> None:
        images_root = self.image_dir / "images"
        if not images_root.exists() or retention_days <= 0:
            return

        cutoff_date = now - timedelta(days=retention_days)
        for date_dir in images_root.iterdir():
            if self._cleanup_budget_exhausted():
                return
            if not date_dir.is_dir():
                continue
            try:
                dir_date = datetime.strptime(date_dir.name, "%Y_%m_%d")
            except ValueError:
                continue
            if dir_date >= cutoff_date:
                continue
            try:
                dir_size = sum(
                    f.stat().st_size for f in date_dir.rglob("*") if f.is_file()
                )
                shutil.rmtree(date_dir)
                self._adjust_dir_size_cache(-dir_size)
                self._files_deleted_this_cycle += 1
                self.logger.info(
                    "Retention cleanup (legacy images): removed %s (%.2f GB, older than %s days)",
                    date_dir.name,
                    dir_size / (1024 ** 3),
                    retention_days,
                )
            except Exception as e:
                self.logger.error(f"Error removing legacy images dir {date_dir}: {e}")

    def _delete_old_files_by_priority(
        self,
        size_violated: bool,
        space_violated: bool,
    ) -> None:
        if not (size_violated or space_violated):
            return

        self.logger.info(
            f"Starting cleanup due to constraints violation: "
            f"size_violated={size_violated}, space_violated={space_violated}"
        )

        deleted_count = 0
        deleted_size = 0

        streams_dir = self.image_dir / "Streams"
        if streams_dir.exists():
            count, size = self._delete_oldest_files(streams_dir, check_constraints=True)
            deleted_count += count
            deleted_size += size
            if count > 0:
                self.logger.info(f"Deleted {count} streaming video files ({size / (1024 ** 2):.2f} MB)")

        if not self._constraints_still_violated():
            self._finalize_priority_cleanup(deleted_count, deleted_size)
            return

        events_dir = self.image_dir / "Events"
        if events_dir.exists():
            for date_dir in events_dir.iterdir():
                if self._cleanup_budget_exhausted():
                    break
                if date_dir.is_dir():
                    videos_dir = date_dir / "Videos"
                    if videos_dir.exists():
                        count, size = self._delete_oldest_files(videos_dir, check_constraints=True)
                        deleted_count += count
                        deleted_size += size
                        if count > 0:
                            self.logger.info(
                                f"Deleted {count} event video files ({size / (1024 ** 2):.2f} MB)"
                            )
                        if not self._constraints_still_violated():
                            self._finalize_priority_cleanup(deleted_count, deleted_size)
                            return

        object_images_retention = self.retention_days.get("object_images", 180)
        if object_images_retention > 0:
            self._delete_legacy_images_by_date(object_images_retention, datetime.now())

        detections_dir = self.image_dir / "Detections"
        if detections_dir.exists() and not self._cleanup_budget_exhausted():
            count, size = self._delete_oldest_files(detections_dir, check_constraints=True)
            deleted_count += count
            deleted_size += size
            if count > 0:
                self.logger.info(f"Deleted {count} object image files ({size / (1024 ** 2):.2f} MB)")
            if not self._constraints_still_violated():
                self._finalize_priority_cleanup(deleted_count, deleted_size)
                return

        if events_dir.exists():
            for date_dir in events_dir.iterdir():
                if self._cleanup_budget_exhausted():
                    break
                if date_dir.is_dir():
                    images_dir = date_dir / "Images"
                    if images_dir.exists():
                        count, size = self._delete_oldest_files(images_dir, check_constraints=True)
                        deleted_count += count
                        deleted_size += size
                        if count > 0:
                            self.logger.info(
                                f"Deleted {count} event image files ({size / (1024 ** 2):.2f} MB)"
                            )
                        if not self._constraints_still_violated():
                            break

        self._finalize_priority_cleanup(deleted_count, deleted_size)

    def _finalize_priority_cleanup(self, deleted_count: int, deleted_size: int) -> None:
        if deleted_count > 0:
            self.logger.info(
                f"Total cleanup: {deleted_count} files deleted, "
                f"{deleted_size / (1024 ** 3):.2f} GB freed"
            )
            self._remove_empty_directories(self.image_dir)
        elif self._constraints_still_violated(refresh_size=True):
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
        data_type: str,
    ) -> None:
        if not base_dir.exists() or retention_days <= 0:
            return

        cutoff_date = now - timedelta(days=retention_days)
        deleted_count = 0
        deleted_size = 0
        active_files_count = 0

        for file_path in self._iter_files(base_dir):
            if self._cleanup_budget_exhausted():
                break
            self._maybe_heartbeat(f"retention {data_type}")

            try:
                file_mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
                file_age_days = (now - file_mtime).days

                if file_mtime < cutoff_date:
                    if not self._is_file_active(file_path):
                        file_size = file_path.stat().st_size
                        file_path.unlink(missing_ok=True)
                        deleted_count += 1
                        deleted_size += file_size
                        self._files_deleted_this_cycle += 1
                        self._adjust_dir_size_cache(-file_size)
                    else:
                        active_files_count += 1
            except Exception as e:
                self.logger.debug(f"Error processing file {file_path} for retention: {e}")

        if deleted_count > 0:
            self.logger.info(
                f"Retention cleanup ({data_type}): {deleted_count} files deleted "
                f"({deleted_size / (1024 ** 2):.2f} MB), older than {retention_days} days"
            )
            self._remove_empty_directories(base_dir)

    def _delete_oldest_files(
        self,
        base_dir: Path,
        check_constraints: bool = False,
    ) -> Tuple[int, int]:
        deleted_count = 0
        deleted_size = 0
        active_files_count = 0

        files_with_mtime: List[Tuple[Path, float, int]] = []
        for file_path in self._iter_files(base_dir):
            try:
                stat = file_path.stat()
                files_with_mtime.append((file_path, stat.st_mtime, stat.st_size))
            except Exception:
                continue

        files_with_mtime.sort(key=lambda x: x[1])
        check_interval = max(10, len(files_with_mtime) // 100) if files_with_mtime else 10

        for idx, (file_path, mtime, file_size) in enumerate(files_with_mtime):
            if self._cleanup_budget_exhausted():
                break
            self._maybe_heartbeat(f"constraints {base_dir.name}")

            if check_constraints and idx > 0 and idx % check_interval == 0:
                if not self._constraints_still_violated():
                    break

            if not self._is_file_active(file_path):
                try:
                    file_path.unlink(missing_ok=True)
                    deleted_count += 1
                    deleted_size += file_size
                    self._files_deleted_this_cycle += 1
                    self._adjust_dir_size_cache(-file_size)
                except Exception as e:
                    self.logger.error(f"Error deleting file {file_path}: {e}", exc_info=True)
            else:
                active_files_count += 1

        if active_files_count > 5:
            self.logger.warning(
                f"Skipped {active_files_count} active files in {base_dir}. "
                f"Storage constraints may be too strict. Consider disabling recording."
            )

        return deleted_count, deleted_size

    def _refresh_newest_streaming_files(self) -> None:
        streams_dir = self.image_dir / "Streams"
        newest: Dict[Path, float] = {}
        if not streams_dir.exists():
            self._newest_streaming_files = newest
            return
        try:
            for cam_dir in streams_dir.iterdir():
                if not cam_dir.is_dir():
                    continue
                latest_mtime = 0.0
                latest_path: Optional[Path] = None
                for file_path in self._iter_files(cam_dir):
                    try:
                        mtime = file_path.stat().st_mtime
                        if mtime >= latest_mtime:
                            latest_mtime = mtime
                            latest_path = file_path
                    except Exception:
                        continue
                if latest_path is not None:
                    newest[cam_dir] = latest_mtime
        except Exception as e:
            self.logger.debug(f"Error scanning newest streaming files: {e}")
        self._newest_streaming_files = newest

    def _is_file_active(self, file_path: Path) -> bool:
        try:
            if not file_path.exists():
                return False

            file_mtime = file_path.stat().st_mtime
            file_age = time.time() - file_mtime
            if file_age < self.active_file_age_seconds:
                return True

            for cam_dir, newest_mtime in self._newest_streaming_files.items():
                try:
                    file_path.relative_to(cam_dir)
                except ValueError:
                    continue
                if abs(file_mtime - newest_mtime) < 1.0:
                    return True

            return False

        except Exception:
            return True

    def _constraints_still_violated(self, refresh_size: bool = False) -> bool:
        try:
            if not self.image_dir.exists():
                return False

            dir_size_gb = self._get_dir_size(
                self.image_dir, force_refresh=refresh_size
            ) / (1024 ** 3)
            if dir_size_gb > self.max_dir_size_gb:
                return True

            free_space_percent = get_disk_free_percent(self.image_dir)
            if free_space_percent < self.min_free_space_percent:
                return True

            return False

        except Exception:
            return False

    def _get_dir_size(self, directory: Path, force_refresh: bool = False) -> int:
        now = time.time()
        if (
            not force_refresh
            and self._dir_size_cache_bytes is not None
            and now - self._dir_size_cache_time < self.dir_size_cache_ttl_seconds
        ):
            return self._dir_size_cache_bytes

        total_size = 0
        try:
            for file_path in self._iter_files(directory):
                try:
                    total_size += file_path.stat().st_size
                except (OSError, PermissionError):
                    pass
        except Exception as e:
            self.logger.debug(f"Error calculating directory size: {e}")

        self._dir_size_cache_bytes = total_size
        self._dir_size_cache_time = now
        return total_size

    def _adjust_dir_size_cache(self, delta_bytes: int) -> None:
        if self._dir_size_cache_bytes is None:
            return
        self._dir_size_cache_bytes = max(0, self._dir_size_cache_bytes + delta_bytes)
        self._dir_size_cache_time = time.time()

    def _iter_files(self, base_dir: Path) -> Iterator[Path]:
        if not base_dir.exists():
            return
        for root, _, files in os.walk(base_dir):
            if self._stop_event.is_set():
                return
            for name in files:
                yield Path(root) / name

    def _remove_empty_directories(self, base_dir: Path) -> None:
        if not base_dir.exists() or not base_dir.is_dir():
            return

        removed_count = 0
        try:
            for root, dirs, files in os.walk(base_dir, topdown=False):
                dir_path = Path(root)
                if dir_path == base_dir:
                    continue
                try:
                    if dir_path.exists() and dir_path.is_dir() and not any(dir_path.iterdir()):
                        dir_path.rmdir()
                        removed_count += 1
                except Exception:
                    pass

            if removed_count > 0:
                self.logger.info(f"Removed {removed_count} empty directories")

        except Exception as e:
            self.logger.debug(f"Error during empty directory cleanup: {e}")
