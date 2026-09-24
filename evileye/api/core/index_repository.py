"""Index build vs project separation (T19).

Singleflight must only wrap full-day builds; callers project by camera after.
"""

from __future__ import annotations

from typing import Any, Callable


def project_event_items(
    items: list[dict[str, Any]],
    cameras: list[str] | None,
) -> list[dict[str, Any]]:
    """Filter event intervals for a caller camera set (empty camera rows kept)."""
    cam_list = [c for c in (cameras or []) if c]
    if not cam_list:
        return list(items)
    cam_set = set(cam_list)
    return [it for it in items if not it.get("camera") or it.get("camera") in cam_set]


def build_then_project(
    build_fn: Callable[[], list[dict[str, Any]]],
    cameras: list[str] | None,
) -> list[dict[str, Any]]:
    """Run a full-index builder then project — never filter inside build_fn."""
    return project_event_items(build_fn(), cameras)
