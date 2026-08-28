"""Zone configuration helpers shared by API editors and runtime control."""
from __future__ import annotations

from typing import Any


def zone_detector_section(body: dict[str, Any]) -> dict[str, Any]:
    events = body.get("events_detectors") or {}
    if not isinstance(events, dict):
        return {}
    section = events.get("ZoneEventsDetector") or {}
    return section if isinstance(section, dict) else {}


def zone_sources_map(body: dict[str, Any]) -> dict[str, Any]:
    section = zone_detector_section(body)
    sources = section.get("sources") or {}
    return sources if isinstance(sources, dict) else {}


def normalize_polygon_coords(entry: Any) -> list[list[float]] | None:
    """Normalize a single zone entry to a list of [x, y] points."""
    if isinstance(entry, dict):
        points = entry.get("points") or entry.get("coords") or entry.get("coordinates")
        if not isinstance(points, list) or not points:
            return None
        return _normalize_point_list(points)
    if isinstance(entry, (list, tuple)) and not entry:
        return None
    if isinstance(entry, (list, tuple)):
        # Unwrap accidental extra nesting: [[[x,y],...]] -> [[x,y],...]
        while (
            len(entry) == 1
            and isinstance(entry[0], (list, tuple))
            and entry[0]
            and isinstance(entry[0][0], (list, tuple))
        ):
            entry = entry[0]
        if entry and isinstance(entry[0], (list, tuple)) and len(entry[0]) >= 2:
            first = entry[0]
            if isinstance(first[0], (int, float)):
                return _normalize_point_list(list(entry))
        return None
    return None


def _normalize_point_list(points: list[Any]) -> list[list[float]] | None:
    out: list[list[float]] = []
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            return None
        try:
            out.append([float(point[0]), float(point[1])])
        except (TypeError, ValueError):
            return None
    return out if len(out) >= 3 else None


def detector_zones_for_source(body: dict[str, Any], source_id: int) -> list[list[list[float]]]:
    """Read zone polygons from ZoneEventsDetector.sources with legacy fallbacks."""
    sources = zone_sources_map(body)
    raw = sources.get(str(source_id), sources.get(source_id, []))
    zones: list[list[list[float]]] = []
    if not isinstance(raw, list):
        return zones
    for entry in raw:
        coords = normalize_polygon_coords(entry)
        if coords:
            zones.append(coords)
    if zones:
        return zones

    # Legacy web editor path
    events = body.get("events_detectors") or {}
    if isinstance(events, dict):
        legacy = events.get("zones") or {}
        if isinstance(legacy, dict):
            raw_legacy = legacy.get(str(source_id), legacy.get(source_id, []))
            if isinstance(raw_legacy, list):
                for entry in raw_legacy:
                    coords = normalize_polygon_coords(entry)
                    if coords:
                        zones.append(coords)
    web_zones = body.get("web_zones")
    if isinstance(web_zones, dict):
        raw_web = web_zones.get(str(source_id), web_zones.get(source_id, []))
        if isinstance(raw_web, list):
            for entry in raw_web:
                coords = normalize_polygon_coords(entry)
                if coords:
                    zones.append(coords)
    return zones


def ui_zones_from_detector(raw_zones: list[list[list[float]]]) -> list[dict[str, Any]]:
    ui: list[dict[str, Any]] = []
    for idx, coords in enumerate(raw_zones):
        ui.append(
            {
                "name": f"zone_{idx + 1}",
                "type": "polygon",
                "points": coords,
            }
        )
    return ui


def ui_zones_to_detector(zones: list[dict[str, Any]]) -> list[list[list[float]]]:
    out: list[list[list[float]]] = []
    for zone in zones or []:
        if not isinstance(zone, dict):
            continue
        coords = normalize_polygon_coords(zone)
        if coords:
            out.append(coords)
    return out


def set_detector_zones_for_source(body: dict[str, Any], source_id: int, zones: list[list[list[float]]]) -> None:
    events = body.setdefault("events_detectors", {})
    if not isinstance(events, dict):
        body["events_detectors"] = {}
        events = body["events_detectors"]
    section = events.setdefault("ZoneEventsDetector", {})
    if not isinstance(section, dict):
        section = {}
        events["ZoneEventsDetector"] = section
    sources = section.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        section["sources"] = sources
    sources[str(source_id)] = zones
