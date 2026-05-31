"""Directory naming helpers for JSON event image storage."""

from __future__ import annotations

import os
from typing import Tuple


def event_image_dirs(day_dir: str, *, is_lost: bool) -> Tuple[str, str]:
    """
    Return (previews_dir, frames_dir) under day_dir/Images for found or lost events.
    """
    images_dir = os.path.join(day_dir, "Images")
    if is_lost:
        return (
            os.path.join(images_dir, "LostPreviews"),
            os.path.join(images_dir, "LostFrames"),
        )
    return (
        os.path.join(images_dir, "FoundPreviews"),
        os.path.join(images_dir, "FoundFrames"),
    )


def ensure_event_image_dirs(day_dir: str, *, is_lost: bool) -> Tuple[str, str]:
    previews_dir, frames_dir = event_image_dirs(day_dir, is_lost=is_lost)
    os.makedirs(previews_dir, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    return previews_dir, frames_dir
