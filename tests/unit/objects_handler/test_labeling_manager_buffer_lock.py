"""Regression: buffer flush must not deadlock on nested buffer_lock."""
from __future__ import annotations

import json
import time
from pathlib import Path

from evileye.objects_handler.labeling_manager import LabelingManager


def _found_row(i: int) -> dict:
    return {
        "object_id": i,
        "timestamp": f"2026-09-08T13:30:{i % 60:02d}.{i:06d}",
        "source_name": "Cam1",
        "class_name": "person",
    }


def _lost_row(i: int) -> dict:
    return {
        "object_id": i,
        "detected_timestamp": f"2026-09-08T13:30:{i % 60:02d}.{i:06d}",
        "lost_timestamp": f"2026-09-08T13:31:{i % 60:02d}.{i:06d}",
        "source_name": "Cam1",
        "class_name": "person",
    }


def test_add_object_found_flush_at_buffer_size_does_not_deadlock(tmp_path):
    manager = LabelingManager(base_dir=str(tmp_path), preload_data=False)
    manager.buffer_size = 100
    try:
        started = time.monotonic()
        for i in range(manager.buffer_size + 1):
            manager.add_object_found(_found_row(i))
        elapsed = time.monotonic() - started
        assert elapsed < 2.0, f"flush hung ({elapsed:.2f}s) — nested buffer_lock deadlock?"
        manager.flush_buffers()
        found_file = Path(tmp_path) / "Detections" / "2026-09-08" / "Metadata" / "objects_found.json"
        assert found_file.is_file()
        data = json.loads(found_file.read_text(encoding="utf-8"))
        assert len(data.get("objects") or []) >= manager.buffer_size
    finally:
        manager.stop()


def test_add_object_lost_flush_at_buffer_size_does_not_deadlock(tmp_path):
    manager = LabelingManager(base_dir=str(tmp_path), preload_data=False)
    manager.buffer_size = 100
    try:
        started = time.monotonic()
        for i in range(manager.buffer_size + 1):
            manager.add_object_lost(_lost_row(i))
        elapsed = time.monotonic() - started
        assert elapsed < 2.0, f"flush hung ({elapsed:.2f}s) — nested buffer_lock deadlock?"
        manager.flush_buffers()
        lost_file = Path(tmp_path) / "Detections" / "2026-09-08" / "Metadata" / "objects_lost.json"
        assert lost_file.is_file()
        data = json.loads(lost_file.read_text(encoding="utf-8"))
        assert len(data.get("objects") or []) >= manager.buffer_size
    finally:
        manager.stop()
