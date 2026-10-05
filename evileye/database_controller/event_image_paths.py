"""Directory naming helpers for JSON event image storage."""

from __future__ import annotations

import os
from typing import Optional, Tuple


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


def write_owner_sidecar(image_abs_path: str, owner: Optional[str]) -> None:
    """Write `<image>.owner` manifest used by media_access ACL (H4)."""
    if not owner or not image_abs_path:
        return
    try:
        with open(str(image_abs_path) + ".owner", "w", encoding="utf-8") as fh:
            fh.write(str(owner).strip() + "\n")
    except Exception:
        pass


def owner_from_event(event) -> Optional[str]:
    """Best-effort camera name for ACL sidecars."""
    name = getattr(event, "source_name", None)
    if name:
        return str(name).strip() or None
    names = getattr(event, "source_names", None)
    if isinstance(names, (list, tuple)) and names:
        return str(names[0]).strip() or None
    img = (
        getattr(event, "img_entered", None)
        or getattr(event, "img_left", None)
        or getattr(event, "img_found", None)
        or getattr(event, "img_finished", None)
        or getattr(event, "img_detected", None)
        or getattr(event, "img_lost", None)
    )
    if img is not None:
        sn = getattr(img, "source_name", None)
        if sn:
            return str(sn).strip() or None
        names = getattr(img, "source_names", None)
        if isinstance(names, (list, tuple)) and names:
            return str(names[0]).strip() or None
    return None
