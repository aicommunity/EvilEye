"""Pure-Python config validation (no Qt dependency). Ported from Configurer validators."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KNOWN_SECTIONS = (
    "sources",
    "detectors",
    "trackers",
    "events_detectors",
    "objects_handler",
    "database",
    "visualizer",
    "pipeline",
    "server",
)

_URL_RE = re.compile(
    r"^(https?|rtsp|rtsps|file)://.+$",
    re.IGNORECASE,
)


def _as_list(section: Any) -> list[Any]:
    if section is None:
        return []
    if isinstance(section, list):
        return section
    if isinstance(section, dict):
        # sources may be {items: [...]} or keyed map
        if "items" in section and isinstance(section["items"], list):
            return section["items"]
        return [section]
    return []


def validate_config(body: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(body, dict):
        return {"ok": False, "errors": ["Config root must be an object"], "warnings": []}

    sources = body.get("sources")
    if sources is None:
        warnings.append("Missing sources section")
    elif not isinstance(sources, (list, dict)):
        errors.append("sources must be list or object")
    else:
        for i, src in enumerate(_as_list(sources)):
            if not isinstance(src, dict):
                errors.append(f"sources[{i}] must be object")
                continue
            uri = src.get("uri") or src.get("url") or src.get("source")
            if uri is not None and isinstance(uri, str) and uri and not _URL_RE.match(uri) and not Path(uri).suffix:
                warnings.append(f"sources[{i}]: unusual URI format '{uri}'")
            sid = src.get("source_id")
            if sid is not None and not isinstance(sid, int):
                try:
                    int(sid)
                except Exception:
                    errors.append(f"sources[{i}].source_id must be int")

    detectors = body.get("detectors")
    if detectors is not None and not isinstance(detectors, list):
        errors.append("detectors must be a list")
    if isinstance(detectors, list):
        for i, det in enumerate(detectors):
            if not isinstance(det, dict):
                errors.append(f"detectors[{i}] must be object")
                continue
            if "model" not in det:
                warnings.append(f"detectors[{i}] missing model")
            else:
                model = det.get("model")
                if isinstance(model, str) and model and not model.endswith((".pt", ".onnx", ".engine", ".xml")):
                    warnings.append(f"detectors[{i}].model unusual extension")
            conf = det.get("conf", det.get("confidence"))
            if conf is not None:
                try:
                    c = float(conf)
                    if not 0.0 <= c <= 1.0:
                        errors.append(f"detectors[{i}].conf must be in [0,1]")
                except (TypeError, ValueError):
                    errors.append(f"detectors[{i}].conf must be numeric")
            roi = det.get("roi")
            if roi is not None and not isinstance(roi, list):
                errors.append(f"detectors[{i}].roi must be a list")
            sids = det.get("source_ids")
            if sids is not None and not isinstance(sids, list):
                errors.append(f"detectors[{i}].source_ids must be a list")

    trackers = body.get("trackers")
    if trackers is not None and not isinstance(trackers, (list, dict)):
        errors.append("trackers must be list or object")

    events = body.get("events_detectors") or body.get("events")
    if events is not None and not isinstance(events, (list, dict)):
        errors.append("events_detectors must be list or object")
    elif isinstance(events, list):
        for i, ev in enumerate(events):
            if not isinstance(ev, dict):
                errors.append(f"events_detectors[{i}] must be object")
                continue
            zones = ev.get("zones")
            if zones is not None and not isinstance(zones, list):
                errors.append(f"events_detectors[{i}].zones must be a list")

    database = body.get("database")
    if database is not None:
        if not isinstance(database, dict):
            errors.append("database must be an object")
        else:
            port = database.get("port")
            if port is not None:
                try:
                    p = int(port)
                    if not 1 <= p <= 65535:
                        errors.append("database.port out of range")
                except (TypeError, ValueError):
                    errors.append("database.port must be int")

    visualizer = body.get("visualizer")
    if visualizer is not None and not isinstance(visualizer, dict):
        errors.append("visualizer must be an object")

    handler = body.get("objects_handler")
    if handler is not None and not isinstance(handler, (dict, list)):
        errors.append("objects_handler must be object or list")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


def list_sections(body: dict[str, Any]) -> list[str]:
    found = [k for k in KNOWN_SECTIONS if k in body]
    for key in body.keys():
        if key not in found and isinstance(body.get(key), (dict, list)):
            found.append(key)
    return found
