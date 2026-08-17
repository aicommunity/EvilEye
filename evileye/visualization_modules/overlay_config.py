"""Shared helpers for overlay metadata from pipeline configuration."""

from __future__ import annotations

from typing import Any


def extract_zones_by_source(params: dict[str, Any] | None) -> dict[int, list]:
    """Zone polygons per source_id from ZoneEventsDetector config."""
    zones_cfg = (
        (((params or {}).get("events_detectors", {}) or {}).get("ZoneEventsDetector", {}) or {}).get("sources", {})
    )
    sources_zones: dict[int, list] = {}
    if isinstance(zones_cfg, dict):
        for key, zone_list in zones_cfg.items():
            try:
                source_id = int(key)
            except Exception:
                continue
            prepared = _prepare_zone_entries(zone_list)
            if prepared:
                sources_zones[source_id] = prepared

    if sources_zones:
        return sources_zones

    # Web config editor / legacy fallbacks (same paths as config_editors API).
    events = (params or {}).get("events_detectors") or {}
    if isinstance(events, dict):
        zones_map = events.get("zones")
        if isinstance(zones_map, dict):
            for key, zone_list in zones_map.items():
                try:
                    source_id = int(key)
                except Exception:
                    continue
                prepared = _prepare_zone_entries(zone_list)
                if prepared:
                    sources_zones[source_id] = prepared

    web_zones = (params or {}).get("web_zones")
    if isinstance(web_zones, dict):
        for key, zone_list in web_zones.items():
            try:
                source_id = int(key)
            except Exception:
                continue
            prepared = _prepare_zone_entries(zone_list)
            if prepared:
                sources_zones[source_id] = prepared

    return sources_zones


def _prepare_zone_entries(zone_list: Any) -> list[list[Any]]:
    prepared: list[list[Any]] = []
    for entry in zone_list or []:
        parsed = _parse_zone_entry(entry)
        if parsed is not None:
            prepared.append(parsed)
    return prepared


def _parse_zone_entry(entry: Any) -> list[Any] | None:
    """Normalize config zone entry to [type, points, extra] tuple."""
    if isinstance(entry, dict):
        points = entry.get("points") or entry.get("coords") or entry.get("coordinates")
        if not isinstance(points, list) or not points:
            return None
        zone_type = entry.get("type") or entry.get("name") or "poly"
        return [str(zone_type), points, None]
    if isinstance(entry, (list, tuple)) and entry:
        if isinstance(entry[0], (list, tuple)) and len(entry[0]) >= 2:
            return ["poly", list(entry), None]
        if len(entry) >= 2 and isinstance(entry[0], str):
            # Already ["poly", coords, extra]
            return list(entry)
    return None


def serialize_zones_for_overlay(
    zones: list[Any] | None,
    img_w: int = 0,
    img_h: int = 0,
    *,
    normalize: bool = True,
) -> list[dict[str, Any]]:
    """Convert internal zone tuples to StreamMetadata zone dicts (normalized 0..1).

    When ``normalize=False``, coords are copied as-is (same as live WS metadata).
    """
    from evileye.visualization_modules.journal_metadata_extractor import EventMetadataExtractor

    out: list[dict[str, Any]] = []
    for zone in zones or []:
        try:
            zone_type, zone_coords, _extra = zone
            norm = None
            if normalize and img_w > 0 and img_h > 0:
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

    pipeline = params.get("pipeline") if isinstance(params.get("pipeline"), dict) else params
    sources = pipeline.get("sources") if isinstance(pipeline, dict) else None
    for source in sources or []:
        if not isinstance(source, dict):
            continue
        source_ids = source.get("source_ids") or []
        if source_id not in source_ids:
            continue
        for key in ("frame_width", "width", "video_width"):
            value = source.get(key)
            if value:
                try:
                    w = int(value)
                except Exception:
                    continue
                if w <= 0:
                    continue
                h = (
                    source.get("frame_height")
                    or source.get("height")
                    or source.get("video_height")
                    or default[1]
                )
                try:
                    h = int(h)
                except Exception:
                    h = default[1]
                if h > 0:
                    return w, h

    vis = params.get("visualization") or params.get("visualizer") or {}
    text_cfg = vis.get("text_config") if isinstance(vis.get("text_config"), dict) else {}
    base = text_cfg.get("base_resolution")
    if isinstance(base, (list, tuple)) and len(base) >= 2:
        try:
            w, h = int(base[0]), int(base[1])
            if w > 0 and h > 0:
                return w, h
        except Exception:
            pass

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
