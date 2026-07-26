"""Unit tests for StorageMonitor cleanup budgets and caching."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from evileye.core.storage_monitor import StorageMonitor


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    root = tmp_path / "EvilEyeData"
    (root / "Streams" / "Cam1").mkdir(parents=True)
    (root / "Detections").mkdir(parents=True)
    (root / "images").mkdir(parents=True)
    return root


def _write_file(path: Path, size: int = 1024, mtime: float | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"x" * size)
    if mtime is not None:
        import os

        os.utime(path, (mtime, mtime))


def test_dir_size_cache_avoids_repeated_walk(monkeypatch, data_root: Path) -> None:
    _write_file(data_root / "Streams" / "Cam1" / "old.mp4", 2048)
    monitor = StorageMonitor(
        str(data_root),
        {
            "enabled": True,
            "dir_size_cache_ttl_seconds": 60,
            "check_interval_seconds": 60,
        },
    )

    walk_calls = {"count": 0}
    original_iter = monitor._iter_files

    def counting_iter(base_dir: Path):
        walk_calls["count"] += 1
        yield from original_iter(base_dir)

    monkeypatch.setattr(monitor, "_iter_files", counting_iter)

    first = monitor._get_dir_size(data_root)
    second = monitor._get_dir_size(data_root)
    assert first == second == 2048
    assert walk_calls["count"] == 1


def test_cleanup_respects_file_budget(data_root: Path) -> None:
    old_mtime = time.time() - 3600
    for i in range(10):
        _write_file(data_root / "Detections" / f"img_{i}.jpg", 1000, old_mtime)

    monitor = StorageMonitor(
        str(data_root),
        {
            "enabled": True,
            "max_files_per_cycle": 3,
            "max_cleanup_seconds": 120,
            "max_dir_size_gb": 0,
            "min_free_space_percent": 0,
            "active_file_age_seconds": 1,
        },
    )
    monitor._begin_cleanup_cycle()
    count, _size = monitor._delete_oldest_files(data_root / "Detections", check_constraints=False)
    assert count == 3
    remaining = list((data_root / "Detections").glob("*.jpg"))
    assert len(remaining) == 7


def test_legacy_images_date_dirs_removed(data_root: Path) -> None:
    old_dir = data_root / "images" / "2020_01_01"
    old_dir.mkdir(parents=True)
    _write_file(old_dir / "frame.jpg", 500, time.time() - 86400 * 400)

    monitor = StorageMonitor(
        str(data_root),
        {
            "enabled": True,
            "max_files_per_cycle": 100,
            "retention_days": {"object_images": 30},
        },
    )
    monitor._begin_cleanup_cycle()
    monitor._delete_legacy_images_by_date(30, datetime.now())
    assert not old_dir.exists()


def test_newest_streaming_segment_not_deleted(data_root: Path) -> None:
    cam_dir = data_root / "Streams" / "Cam1"
    now = time.time()
    _write_file(cam_dir / "old_segment.mp4", 1000, now - 3600)
    _write_file(cam_dir / "new_segment.mp4", 1000, now - 5)

    monitor = StorageMonitor(
        str(data_root),
        {
            "enabled": True,
            "active_file_age_seconds": 30,
            "max_dir_size_gb": 0,
            "min_free_space_percent": 0,
        },
    )
    monitor._begin_cleanup_cycle()
    monitor._delete_oldest_files(cam_dir, check_constraints=False)

    assert not (cam_dir / "old_segment.mp4").exists()
    assert (cam_dir / "new_segment.mp4").exists()


def test_is_file_active_skips_recent_mtime(data_root: Path) -> None:
    cam_dir = data_root / "Streams" / "Cam1"
    recent = cam_dir / "recent.mp4"
    old = cam_dir / "old.mp4"
    _write_file(recent, 100, time.time() - 5)
    _write_file(old, 100, time.time() - 120)

    monitor = StorageMonitor(str(data_root), {"active_file_age_seconds": 60})
    assert monitor._is_file_active(recent) is True

    monitor._refresh_newest_streaming_files()
    assert monitor._is_file_active(recent) is True
    assert monitor._is_file_active(old) is False
