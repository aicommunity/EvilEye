"""Retention caps for active history / last_image under object storms."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np

from evileye.objects_handler.objects_handler import ObjectsHandler


def _make_handler(**overrides):
    handler = ObjectsHandler(db_controller=None, db_adapter=None)
    handler.labeling_manager = MagicMock()
    handler.save_object_images = False
    handler.save_labeling_data = False
    handler.lost_thresh = 5
    handler._use_object_pool = False
    handler.history_len = overrides.get("history_len", 30)
    handler.max_history_items_total = overrides.get("max_history_items_total", 240)
    handler.max_active_last_image_mb = overrides.get("max_active_last_image_mb", 96.0)
    return handler


def _track(track_id):
    return SimpleNamespace(
        track_id=track_id,
        class_id=0,
        bounding_box=[10, 20, 30, 40],
        confidence=0.8,
        tracking_data={},
    )


def _tracking(tracks, source_id=0, frame_id=5):
    return SimpleNamespace(
        source_id=source_id,
        frame_id=frame_id,
        time_stamp=None,
        tracks=tracks,
    )


def _image(frame_id=5, *, unique=True, height=64, width=64):
    pixels = np.zeros((height, width, 3), dtype=np.uint8)
    if unique:
        pixels[0, 0, 0] = frame_id % 255
    return SimpleNamespace(
        source_id=0,
        frame_id=frame_id,
        current_video_position=0,
        image=pixels,
        width=width,
        height=height,
        pts_ns=None,
        media_pts_sec=None,
    )


def test_history_budget_drops_oldest_under_storm():
    handler = _make_handler(history_len=30, max_history_items_total=20)
    # Seed 5 active objects with long histories via repeated updates.
    for frame_id in range(1, 12):
        tracks = [_track(i) for i in range(5)]
        handler._handle_active(_tracking(tracks, frame_id=frame_id), _image(frame_id))
    total_hist = sum(len(obj.history) for obj in handler.active_objs.objects)
    assert total_hist <= 20
    assert len(handler.active_objs.objects) == 5
    # Detection still keeps current track state.
    assert all(obj.track is not None for obj in handler.active_objs.objects)


def test_last_image_budget_drops_unique_frames():
    handler = _make_handler(max_active_last_image_mb=0.01)  # ~10 KiB
    shared = _image(frame_id=1, height=64, width=64)
    handler._handle_active(
        _tracking([_track(i) for i in range(6)], frame_id=1),
        shared,
    )
    # Replace the shared ref with distinct ndarrays to simulate staggered updates.
    for i, obj in enumerate(handler.active_objs.objects):
        obj.last_image = SimpleNamespace(
            image=np.full((64, 64, 3), i, dtype=np.uint8),
            width=64,
            height=64,
        )
        obj.last_update = True
        obj.lost_frames = 0
    handler._enforce_last_image_budget()
    stats = handler.get_runtime_stats()
    assert stats["active_last_image_unique_bytes"] <= int(0.01 * 1024 * 1024) + 4096
    # Objects remain tracked; only pixel retention is capped.
    assert len(handler.active_objs.objects) == 6


def test_finalize_lost_clears_history_and_last_image():
    handler = _make_handler(history_len=5)
    handler._handle_active(_tracking([_track(1)], frame_id=1), _image(1))
    obj = handler.active_objs.objects[0]
    for frame_id in range(2, 6):
        handler._handle_active(_tracking([_track(1)], frame_id=frame_id), _image(frame_id))
    assert len(obj.history) >= 3
    handler._finalize_lost_object(obj, _tracking([], frame_id=6))
    assert obj.last_image is None
    assert obj.history == []
    assert obj in handler.lost_objs.objects
