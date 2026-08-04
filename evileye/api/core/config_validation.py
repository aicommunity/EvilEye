"""Pure-Python config validation (no Qt dependency)."""
from __future__ import annotations

from typing import Any


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
            roi = det.get("roi")
            if roi is not None and not isinstance(roi, list):
                errors.append(f"detectors[{i}].roi must be a list")

    return {"ok": len(errors) == 0, "errors": errors, "warnings": warnings}


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


def list_sections(body: dict[str, Any]) -> list[str]:
    found = [k for k in KNOWN_SECTIONS if k in body]
    # Also include any top-level keys that look like sections
    for key in body.keys():
        if key not in found and isinstance(body.get(key), (dict, list)):
            found.append(key)
    return found
