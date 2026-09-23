"""Shared media / camera path ACL helpers (audit Stage 3).

Keeps REST playback media checks aligned with hard camera ACL.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException

from evileye.api.core.camera_access import CameraAccess, assert_name_allowed


def cameras_from_media_path(path: str) -> list[str] | None:
    """Extract logical camera names from archive path.

    Streams/YYYY-MM-DD/<Cam or CamA-CamB>/file → [Cam] or [CamA, CamB].
    Events/.../<camera>/... → [camera] when present.
    Returns None when cameras cannot be determined.
    """
    try:
        parts = Path(path).parts
    except Exception:
        return None
    for i, part in enumerate(parts):
        if part == "Streams" and i + 2 < len(parts):
            folder = parts[i + 2]
            if not folder or folder in {".", ".."}:
                return None
            if "-" in folder:
                names = [p for p in folder.split("-") if p]
                return names or None
            return [folder]
        if part == "Events" and i + 2 < len(parts):
            folder = parts[i + 2]
            if folder and folder not in {".", "..", "Metadata", "Images"}:
                return [folder]
    return None


def assert_media_path_allowed(access: CameraAccess, path: str) -> None:
    """Hard ACL for playback media: composite requires all parts."""
    cams = cameras_from_media_path(path)
    if access.unrestricted:
        return
    if not cams:
        raise HTTPException(status_code=403, detail="Camera access denied")
    for name in cams:
        assert_name_allowed(access, name)
