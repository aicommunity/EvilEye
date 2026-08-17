"""Shared helpers for overlay metadata from pipeline configuration."""

from __future__ import annotations

from typing import Any


def extract_zones_by_source(params: dict[str, Any] | None) -> dict[int, list]:
    """Zone polygons per source_id from ZoneEventsDetector config."""
    zones_cfg = (
        (((params or {}).get("events_detectors", {}) or {}).get("ZoneEventsDetector", {}) or {}).get("sources", {})
    )
    sources_zones: dict[int, list] = {}
    if not isinstance(zones_cfg, dict):
        return sources_zones
    for key, zone_list in zones_cfg.items():
        try:
            source_id = int(key)
        except Exception:
            continue
        prepared = []
        for coords in zone_list or []:
            if isinstance(coords, list) and coords:
                prepared.append(["poly", coords, None])
        if prepared:
            sources_zones[source_id] = prepared
    return sources_zones


def serialize_zones_for_overlay(
    zones: list[Any] | None,
    img_w: int = 0,
    img_h: int = 0,
) -> list[dict[str, Any]]:
    """Convert internal zone tuples to StreamMetadata zone dicts (normalized 0..1)."""
    from evileye.visualization_modules.journal_metadata_extractor import EventMetadataExtractor

    out: list[dict[str, Any]] = []
    for zone in zones or []:
        try:
            zone_type, zone_coords, _extra = zone
            norm = None
            if img_w > 0 and img_h > 0:
                norm = EventMetadataExtractor.normalize_zone_coords(zone_coords, img_w, img_h)
            if norm:
                points = [[float(px), float(py)] for px, py in norm]
            else:
                points = []
                for px, py in zone_coords or []:
                    points.append([float(px), float(py)])
            if points:
                out.append({"name": str(zone_type), "points": points})
        except Exception:
            continue
    return out


def video_size_for_source(params: dict[str, Any] | None, source_id: int | None) -> tuple[int, int]:
    """Best-effort native frame size for coordinate normalization."""
    default = (1920, 1080)
    if not params or source_id is None:
        return default

    vis = params.get("visualization") or {}
    base = vis.get("text_config", {}).get("base_resolution") if isinstance(vis.get("text_config"), dict) else None
    if isinstance(base, (list, tuple)) and len(base) >= 2:
        try:
            w, h = int(base[0]), int(base[1])
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass

    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        source_ids = source.get("source_ids") or []
        if source_id not in source_ids:
            continue
        for key in ("width", "frame_width", "video_width"):
            value = source.get(key)
            if value:
                w = int(value)
                h_key = key.replace("width", "height").replace("frame_width", "frame_height")
                h = source.get(h_key) or source.get("height") or source.get("frame_height") or default[1]
                return w, int(h)
    return default


def extract_debug_rois_from_params(
    params: dict[str, Any] | None,
    *,
    source_id: int | None,
    img_w: int,
    img_h: int,
) -> list[list[float]]:
    """Detector ROI rectangles from static config (normalized 0..1)."""
    if not params or source_id is None or img_w <= 0 or img_h <= 0:
        return []

    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    detectors = pipeline.get("detectors") if isinstance(pipeline, dict) else None
    rois_out: list[list[float]] = []
    for detector in detectors or []:
        if not isinstance(detector, dict):
            continue
        source_ids = detector.get("source_ids") or []
        if source_id not in source_ids:
            continue
        try:
            source_idx = source_ids.index(source_id)
        except ValueError:
            continue
        roi_groups = detector.get("roi") or []
        if not isinstance(roi_groups, list) or source_idx not in range(len(roi_groups)):
            continue
        for roi in roi_groups[source_idx] or []:
            if not isinstance(roi, (list, tuple)) or len(roi) < 4:
                continue
            try:
                x, y, rw, rh = [float(v) for v in roi[:4]]
            except Exception:
                continue
            if max(x, y, rw, rh) > 1.5:
                x1 = x / float(img_w)
                y1 = y / float(img_h)
                x2 = (x + rw) / float(img_w)
                y2 = (y + rh) / float(img_h)
            else:
                x1, y1, x2, y2 = x, y, x + rw, y + rh
            rois_out.append([x1, y1, x2, y2])
    return rois_out
