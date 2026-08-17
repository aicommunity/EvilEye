"""Coordinate-space resolution for archive playback overlay (logical frame parity with live)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evileye.visualization_modules.overlay_config import video_size_for_source


@dataclass(frozen=True)
class PlaybackCoordContext:
    camera: str
    source_id: int | None
    logical_w: int
    logical_h: int
    parent_w: int | None
    parent_h: int | None
    src_coords: tuple[int, int, int, int] | None
    is_split: bool


def _pipeline_sources(params: dict[str, Any] | None) -> list[dict[str, Any]]:
    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    if not isinstance(sources, list):
        return []
    return [s for s in sources if isinstance(s, dict)]


def _resolve_source_id_from_params(
    params: dict[str, Any],
    camera: str,
    source_id: int | None,
) -> int | None:
    if source_id is not None:
        return source_id
    for source in _pipeline_sources(params):
        names = source.get("source_names") or []
        ids = source.get("source_ids") or []
        for idx, name in enumerate(names):
            if str(name) == camera and idx < len(ids):
                try:
                    return int(ids[idx])
                except Exception:
                    return None
        split = bool(source.get("split"))
        num_split = int(source.get("num_split") or len(names) or 0)
        if split and num_split and names:
            parent_folder = "-".join(str(n) for n in names[:num_split])
            if camera == parent_folder:
                try:
                    return int(ids[0]) if ids else None
                except Exception:
                    return None
    return None


def _find_split_descriptor(
    params: dict[str, Any],
    source_id: int | None,
    camera: str,
) -> tuple[bool, tuple[int, int, int, int] | None]:
    for source in _pipeline_sources(params):
        names = [str(n) for n in (source.get("source_names") or [])]
        ids = source.get("source_ids") or []
        split = bool(source.get("split"))
        if not split:
            continue
        src_coords_list = source.get("src_coords") or []
        idx: int | None = None
        if source_id is not None and source_id in ids:
            idx = ids.index(source_id)
        elif camera in names:
            idx = names.index(camera)
        if idx is None or idx >= len(src_coords_list):
            continue
        raw = src_coords_list[idx]
        if isinstance(raw, (list, tuple)) and len(raw) >= 4:
            try:
                coords = (int(raw[0]), int(raw[1]), int(raw[2]), int(raw[3]))
                if coords[2] > 0 and coords[3] > 0:
                    return True, coords
            except Exception:
                continue
    return False, None


def source_aliases(
    params: dict[str, Any],
    camera: str,
    source_id: int | None,
) -> set[str]:
    """Acceptable source_name values when filtering archive detection records.

    Sibling split cameras (Cam4 vs Cam5) are not aliases of each other.
    The parent folder name (Cam4-Cam5) is accepted so records stored under
    the composite source still match; ``source_id`` then disambiguates.
    """
    aliases: set[str] = {camera}
    resolved = _resolve_source_id_from_params(params, camera, source_id)
    for source in _pipeline_sources(params):
        names = [str(n) for n in (source.get("source_names") or [])]
        ids = source.get("source_ids") or []
        split = bool(source.get("split"))
        num_split = int(source.get("num_split") or len(names) or 0)
        parent = "-".join(names[:num_split]) if split and num_split else None
        in_group = camera in names or (parent is not None and camera == parent)
        if resolved is not None and resolved in ids:
            idx = ids.index(resolved)
            if idx < len(names):
                aliases.add(names[idx])
            in_group = True
        if in_group and parent:
            aliases.add(parent)
    return aliases


def resolve_playback_coord_context(
    params: dict[str, Any],
    *,
    camera: str,
    source_id: int | None,
    frame_w: int | None,
    frame_h: int | None,
) -> PlaybackCoordContext:
    """Resolve logical-frame pixel size for metadata normalization (live parity)."""
    resolved_source_id = _resolve_source_id_from_params(params, camera, source_id)
    is_split, src_coords = _find_split_descriptor(params, resolved_source_id, camera)

    client_w = client_h = 0
    try:
        client_w = int(frame_w) if frame_w is not None else 0
        client_h = int(frame_h) if frame_h is not None else 0
    except Exception:
        client_w = client_h = 0

    parent_w = client_w if client_w > 0 else None
    parent_h = client_h if client_h > 0 else None

    if is_split and src_coords:
        logical_w, logical_h = int(src_coords[2]), int(src_coords[3])
    elif client_w > 0 and client_h > 0:
        logical_w, logical_h = client_w, client_h
    else:
        logical_w, logical_h = video_size_for_source(params, resolved_source_id)

    return PlaybackCoordContext(
        camera=camera,
        source_id=resolved_source_id,
        logical_w=logical_w,
        logical_h=logical_h,
        parent_w=parent_w,
        parent_h=parent_h,
        src_coords=src_coords,
        is_split=is_split,
    )
