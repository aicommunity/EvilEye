"""Shared media / camera path ACL helpers.

Authorization must run on the canonical path after resolve(), never on the
raw client string (reaudit R01/R02).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from fastapi import HTTPException

from evileye.api.core.camera_access import CameraAccess, assert_name_allowed

# Extensions served as media; Metadata JSON is never a video/image body.
_VIDEO_EXT = {".mp4", ".mkv", ".avi", ".mov", ".webm", ".m4v"}
_IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}
_ALLOWED_ROOTS = frozenset({"Streams", "Events"})


@dataclass(frozen=True)
class ResolvedMedia:
    path: Path
    rel_parts: tuple[str, ...]
    owners: list[str]
    kind: str  # video | image | other


def cameras_from_media_path(path: str) -> list[str] | None:
    """Extract logical camera names from a path string (pre-resolve heuristic).

    Prefer cameras_from_canonical() after resolve for ACL decisions.
    """
    try:
        parts = Path(path).parts
    except Exception:
        return None
    return _cameras_from_parts(parts)


def _cameras_from_parts(parts: tuple[str, ...] | list[str]) -> list[str] | None:
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
            # Events/<date>/Videos/<Cam>/file.mp4 → [Cam]
            if folder == "Videos" and i + 4 < len(parts):
                cam = parts[i + 3]
                if cam and cam not in {".", ".."}:
                    return [cam]
                return None
            if folder in {".", "..", "Metadata", "Images", "Videos"}:
                return None
            return [folder]
    return None


def cameras_from_canonical(resolved: Path, data_root: Path) -> list[str] | None:
    """Owners derived from path relative to data root after resolve()."""
    try:
        rel = resolved.resolve().relative_to(data_root.resolve())
    except Exception:
        return None
    return _cameras_from_parts(rel.parts)


def classify_media_kind(resolved: Path, rel_parts: tuple[str, ...]) -> str:
    """Classify archive file; Metadata/*.json is never serveable as video."""
    if "Metadata" in rel_parts:
        return "forbidden"
    ext = resolved.suffix.lower()
    if ext in _VIDEO_EXT:
        return "video"
    if ext in _IMAGE_EXT:
        return "image"
    return "other"


def resolve_under_data_root(raw_path: str, data_root: Path) -> Path:
    """Resolve raw client path under data_root; raise PermissionError if outside."""
    base = data_root.resolve()
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = base / raw_path
    resolved = candidate.resolve()
    if not str(resolved).startswith(str(base) + os.sep) and resolved != base:
        raise PermissionError(f"Path outside data dir: {raw_path}")
    try:
        rel = resolved.relative_to(base)
    except ValueError as exc:
        raise PermissionError(f"Path outside data dir: {raw_path}") from exc
    parts = rel.parts
    if not parts or parts[0] not in _ALLOWED_ROOTS:
        raise PermissionError(f"Media path not under Streams/Events: {raw_path}")
    return resolved


def assert_resolved_media_allowed(
    access: CameraAccess,
    resolved: Path,
    *,
    data_root: Path,
    allow_kinds: frozenset[str] | None = None,
) -> ResolvedMedia:
    """Enforce root/type/ACL on an already-canonical path under data_root."""
    kinds = allow_kinds or frozenset({"video", "image"})
    base = data_root.resolve()
    try:
        canon = resolved.resolve()
        rel = canon.relative_to(base)
    except Exception as exc:
        raise HTTPException(status_code=403, detail="Path outside data dir") from exc
    rel_parts = tuple(rel.parts)
    if not rel_parts or rel_parts[0] not in _ALLOWED_ROOTS:
        raise HTTPException(status_code=403, detail="Camera access denied")
    kind = classify_media_kind(canon, rel_parts)
    if kind == "forbidden" or kind not in kinds:
        raise HTTPException(status_code=403, detail="Camera access denied")
    owners = cameras_from_canonical(canon, base)
    if access.unrestricted:
        return ResolvedMedia(path=canon, rel_parts=rel_parts, owners=owners or [], kind=kind)
    if not owners:
        raise HTTPException(status_code=403, detail="Camera access denied")
    for name in owners:
        assert_name_allowed(access, name)
    return ResolvedMedia(path=canon, rel_parts=rel_parts, owners=owners, kind=kind)


def resolve_authorized_media(
    access: CameraAccess,
    raw_path: str,
    *,
    data_root: Path,
    allow_kinds: frozenset[str] | None = None,
) -> ResolvedMedia:
    """Canonicalize then enforce root/type/ACL. Raises HTTPException on deny."""
    try:
        resolved = resolve_under_data_root(raw_path, data_root)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return assert_resolved_media_allowed(
        access, resolved, data_root=data_root, allow_kinds=allow_kinds
    )


def assert_media_path_allowed(access: CameraAccess, path: str) -> None:
    """Hard ACL for playback media using canonical path when possible.

    Falls back to string parse only if path cannot be resolved yet (tests).
    Prefer resolve_authorized_media() at HTTP boundaries.
    """
    from evileye.api.core.playback_service import data_dir

    try:
        resolve_authorized_media(access, path, data_root=data_dir())
    except HTTPException:
        raise
    except Exception:
        # Legacy fallback for callers without a data root on disk.
        cams = cameras_from_media_path(path)
        if access.unrestricted:
            return
        if not cams:
            raise HTTPException(status_code=403, detail="Camera access denied")
        for name in cams:
            assert_name_allowed(access, name)
