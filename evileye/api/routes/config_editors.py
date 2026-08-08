"""Config section merge + ROI/zones/class-mapping editors."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from evileye.api.core.config_validation import (
    get_by_path,
    list_sections,
    list_studio_tabs,
    path_exists,
    set_by_path,
    split_path,
    validate_config,
)
router = APIRouter(prefix="/api/v1/configs", tags=["config-editors"])


def _config_path(name: str) -> Path:
    safe = Path(name).name
    path = Path("configs") / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Config '{safe}' not found")
    return path


def _load(name: str) -> dict[str, Any]:
    path = _config_path(name)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid JSON: {exc}") from exc


def _save(name: str, body: dict[str, Any]) -> None:
    path = _config_path(name)
    path.write_text(json.dumps(body, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


class SectionUpdate(BaseModel):
    body: Any = Field(...)


class RoiUpdate(BaseModel):
    rois: list[list[float]] = Field(default_factory=list)


class ZoneItem(BaseModel):
    name: str | None = None
    type: str = "polygon"
    points: list[list[float]]


class ZonesUpdate(BaseModel):
    zones: list[ZoneItem] = Field(default_factory=list)


class ClassMappingUpdate(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


@router.get("/{name}/sections")
async def get_sections(name: str) -> dict:
    body = _load(name)
    return {"sections": list_sections(body), "tabs": list_studio_tabs(body)}


def _resolve_section_key(body: dict[str, Any], section: str) -> str:
    """Accept top-level keys, dotted paths, or studio tab ids (e.g. sources → pipeline.sources)."""
    from evileye.api.core.config_validation import STUDIO_TAB_SPECS, resolve_section_path

    try:
        split_path(section)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if path_exists(body, section):
        return section
    if "." not in section and section in body:
        return section
    for tab_id, candidates in STUDIO_TAB_SPECS:
        if section == tab_id or section in candidates:
            resolved = resolve_section_path(body, candidates)
            if resolved:
                return resolved
    raise HTTPException(status_code=404, detail=f"Section '{section}' not found")


@router.get("/{name}/sections/{section}")
async def get_section(name: str, section: str) -> Any:
    body = _load(name)
    key = _resolve_section_key(body, section)
    try:
        return get_by_path(body, key) if "." in key else body[key]
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Section '{section}' not found") from exc


@router.put("/{name}/sections/{section}")
async def put_section(name: str, section: str, payload: SectionUpdate) -> dict:
    body = _load(name)
    try:
        key = _resolve_section_key(body, section)
    except HTTPException:
        # Allow creating a new top-level / dotted section that does not exist yet.
        try:
            split_path(section)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        key = section
    if "." in key:
        set_by_path(body, key, payload.body)
    else:
        body[key] = payload.body
    _save(name, body)
    return {"name": name, "section": key, "status": "updated"}


@router.post("/{name}/validate")
async def validate_named_config(name: str) -> dict:
    body = _load(name)
    return validate_config(body)


def _detector_for_source(body: dict[str, Any], source_id: int) -> dict[str, Any] | None:
    detectors = body.get("detectors")
    if not isinstance(detectors, list):
        pipe = body.get("pipeline")
        detectors = pipe.get("detectors") if isinstance(pipe, dict) else None
    if not isinstance(detectors, list):
        return None
    for det in detectors:
        if not isinstance(det, dict):
            continue
        source_ids = det.get("source_ids") or []
        if source_id in source_ids or not source_ids:
            return det
    return detectors[0] if detectors else None


@router.get("/{name}/sources/{source_id}/roi")
async def get_roi(name: str, source_id: int) -> dict:
    body = _load(name)
    det = _detector_for_source(body, source_id)
    rois = (det or {}).get("roi") or []
    if not isinstance(rois, list):
        rois = []
    return {"rois": rois}


@router.put("/{name}/sources/{source_id}/roi")
async def put_roi(name: str, source_id: int, payload: RoiUpdate) -> dict:
    body = _load(name)
    det = _detector_for_source(body, source_id)
    if det is None:
        raise HTTPException(status_code=404, detail="No detector for source")
    det["roi"] = payload.rois
    _save(name, body)
    return {"rois": payload.rois, "status": "updated", "restart_required": True}


def _events_zones(body: dict[str, Any], source_id: int) -> list:
    # Prefer events_detectors / zone params commonly used in EvilEye configs
    events = body.get("events_detectors") or body.get("events") or {}
    if isinstance(events, list):
        for item in events:
            if isinstance(item, dict) and source_id in (item.get("source_ids") or [source_id]):
                return item.get("zones") or item.get("params", {}).get("zones") or []
        return []
    if isinstance(events, dict):
        zones = events.get("zones") or {}
        if isinstance(zones, dict):
            return zones.get(str(source_id), zones.get(source_id, []))
        if isinstance(zones, list):
            return zones
    return []


def _set_events_zones(body: dict[str, Any], source_id: int, zones: list) -> None:
    events = body.get("events_detectors")
    if isinstance(events, list) and events:
        target = None
        for item in events:
            if isinstance(item, dict) and source_id in (item.get("source_ids") or []):
                target = item
                break
        target = target or (events[0] if isinstance(events[0], dict) else None)
        if target is not None:
            params = target.setdefault("params", {})
            if isinstance(params, dict):
                params["zones"] = zones
            else:
                target["zones"] = zones
            return
    # Fallback store
    store = body.setdefault("events_detectors", {})
    if isinstance(store, dict):
        zones_map = store.setdefault("zones", {})
        if isinstance(zones_map, dict):
            zones_map[str(source_id)] = zones
        else:
            store["zones"] = zones
    else:
        body["web_zones"] = {str(source_id): zones}


@router.get("/{name}/sources/{source_id}/zones")
async def get_zones(name: str, source_id: int) -> dict:
    body = _load(name)
    raw = _events_zones(body, source_id)
    zones = []
    for z in raw if isinstance(raw, list) else []:
        if isinstance(z, dict):
            zones.append(
                {
                    "name": z.get("name"),
                    "type": z.get("type") or "polygon",
                    "points": z.get("points") or z.get("coords") or [],
                }
            )
    return {"zones": zones}


@router.put("/{name}/sources/{source_id}/zones")
async def put_zones(name: str, source_id: int, payload: ZonesUpdate) -> dict:
    body = _load(name)
    zones = [z.model_dump() for z in payload.zones]
    _set_events_zones(body, source_id, zones)
    _save(name, body)
    return {"zones": zones, "status": "updated", "restart_required": True}


@router.get("/{name}/class-mapping")
async def get_class_mapping(name: str) -> dict:
    body = _load(name)
    mapping = body.get("class_mapping") or body.get("visualizer", {}).get("class_mapping") or {}
    if not isinstance(mapping, dict):
        mapping = {}
    return {"mapping": {str(k): str(v) for k, v in mapping.items()}}


@router.put("/{name}/class-mapping")
async def put_class_mapping(name: str, payload: ClassMappingUpdate) -> dict:
    body = _load(name)
    body["class_mapping"] = payload.mapping
    vis = body.get("visualizer")
    if isinstance(vis, dict):
        vis["class_mapping"] = payload.mapping
    _save(name, body)
    return {"status": "updated", "restart_required": True}
