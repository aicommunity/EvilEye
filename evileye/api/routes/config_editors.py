"""Config section merge + ROI/zones/class-mapping editors."""
from __future__ import annotations

import json
from pathlib import Path
from evileye.core.paths import configs_dir
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
from evileye.api.core.control_ipc import send_control_command
from evileye.api.core.roi_config import (
    detector_entry_for_source,
    detector_rois_for_source,
    display_rois_for_source,
    roi_coord_ref,
    set_detector_rois_for_source,
    ui_pixels_from_rois,
    ui_rois_from_detector,
    ui_rois_to_detector,
)
from evileye.api.core.schedule_alarm_config import (
    get_effective_source_schedule,
    get_global_schedule_alarm_params,
    set_global_schedule_alarm_params,
    set_source_schedule_override,
    source_has_override,
    validate_schedule_alarm_section,
    schedule_alarm_detector_section,
)
from evileye.api.core.zone_config import (
    detector_zones_for_source,
    set_detector_zones_for_source,
    set_zone_detector_params,
    ui_zones_from_detector,
    ui_zones_to_detector,
    zone_detector_params,
)
router = APIRouter(prefix="/api/v1/configs", tags=["config-editors"])


def _config_path(name: str) -> Path:
    safe = Path(name).name
    path = configs_dir() / safe
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
    coord_ref: dict[str, int] | None = None


class ZoneItem(BaseModel):
    name: str | None = None
    type: str = "polygon"
    points: list[list[float]]


class ZonesUpdate(BaseModel):
    zones: list[ZoneItem] = Field(default_factory=list)


class ZoneDetectorParamsUpdate(BaseModel):
    event_threshold: int = Field(ge=0, default=2)
    zone_left_threshold: int = Field(ge=0, default=3)


class ClassMappingUpdate(BaseModel):
    mapping: dict[str, str] = Field(default_factory=dict)


class SourceScheduleModel(BaseModel):
    enabled: bool = True
    weekdays: list[int] = Field(default_factory=lambda: list(range(7)))
    periods: list[list[str]] = Field(default_factory=list)
    class_ids: list[int] = Field(default_factory=list)


class ScheduleAlarmGlobalUpdate(BaseModel):
    camera_cooldown_sec: int = Field(ge=0, default=0)
    default_schedule: SourceScheduleModel


class ScheduleAlarmSourceUpdate(BaseModel):
    schedule: SourceScheduleModel | None = None


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
    if detector_entry_for_source(body, source_id) is None:
        raise HTTPException(status_code=404, detail="No detector for source")
    return {
        "rois": ui_rois_from_detector(body, source_id),
        "display_rois": display_rois_for_source(body, source_id),
        "rois_pixel": detector_rois_for_source(body, source_id),
        "coord_ref": roi_coord_ref(body, source_id),
    }


@router.put("/{name}/sources/{source_id}/roi")
async def put_roi(name: str, source_id: int, payload: RoiUpdate) -> dict:
    body = _load(name)
    if detector_entry_for_source(body, source_id) is None:
        raise HTTPException(status_code=404, detail="No detector for source")
    ui_rois = payload.rois
    coord_ref = payload.coord_ref or {}
    ref_w = int(coord_ref.get("w") or 0)
    ref_h = int(coord_ref.get("h") or 0)
    if ref_w > 0 and ref_h > 0:
        rois_xywh = ui_pixels_from_rois(ui_rois, ref_w, ref_h)
    else:
        rois_xywh = ui_rois_to_detector(body, source_id, ui_rois)
    set_detector_rois_for_source(body, source_id, rois_xywh)
    _save(name, body)
    applied = False
    if _find_runtime_id_for_config(name) is not None:
        applied = _apply_roi_runtime(source_id, rois_xywh)
    apply_meta = _runtime_apply_result(name, applied)
    return {
        "rois": ui_rois,
        "status": "updated",
        **apply_meta,
    }


def _events_zones(body: dict[str, Any], source_id: int) -> list:
    return detector_zones_for_source(body, source_id)


def _set_events_zones(body: dict[str, Any], source_id: int, zones: list[list[list[float]]]) -> None:
    set_detector_zones_for_source(body, source_id, zones)


def _find_runtime_id_for_config(config_name: str) -> int | None:
    try:
        from evileye.api.core.server_state import list_active_run_summaries

        safe_name = Path(config_name).name
        for run in list_active_run_summaries():
            cfg = str(run.get("config_path") or "")
            if not cfg:
                continue
            if Path(cfg).name == safe_name:
                rid = run.get("id")
                if rid is not None:
                    return int(rid)
    except Exception:
        return None
    return None


def _apply_roi_runtime(source_id: int, rois_xywh: list[list[float]]) -> bool:
    response = send_control_command(
        {
            "cmd": "apply_roi",
            "source_id": int(source_id),
            "rois": rois_xywh,
        }
    )
    return bool(isinstance(response, dict) and response.get("ok"))


def _apply_schedule_alarm_runtime(scope: str, **kwargs) -> bool:
    response = send_control_command({"cmd": "apply_schedule_alarm", "scope": scope, **kwargs})
    return bool(isinstance(response, dict) and response.get("ok"))


def _apply_zones_runtime(source_id: int, zones: list[list[list[float]]]) -> bool:
    response = send_control_command(
        {
            "cmd": "apply_zones",
            "source_id": int(source_id),
            "zones": zones,
        }
    )
    return bool(isinstance(response, dict) and response.get("ok"))


def _apply_zone_detector_params_runtime(event_threshold: int, zone_left_threshold: int) -> bool:
    response = send_control_command(
        {
            "cmd": "apply_zone_detector_params",
            "event_threshold": int(event_threshold),
            "zone_left_threshold": int(zone_left_threshold),
        }
    )
    return bool(isinstance(response, dict) and response.get("ok"))


def _runtime_apply_result(config_name: str, applied: bool) -> dict[str, bool]:
    has_run = _find_runtime_id_for_config(config_name) is not None
    restart_required = not applied if has_run else True
    return {
        "restart_required": restart_required,
        "applied_live": applied and has_run,
    }


@router.get("/{name}/sources/{source_id}/zones")
async def get_zones(name: str, source_id: int) -> dict:
    body = _load(name)
    raw = _events_zones(body, source_id)
    return {"zones": ui_zones_from_detector(raw)}


@router.put("/{name}/sources/{source_id}/zones")
async def put_zones(name: str, source_id: int, payload: ZonesUpdate) -> dict:
    body = _load(name)
    ui_zones = [z.model_dump() for z in payload.zones]
    detector_zones = ui_zones_to_detector(ui_zones)
    _set_events_zones(body, source_id, detector_zones)
    _save(name, body)
    applied = False
    if _find_runtime_id_for_config(name) is not None:
        applied = _apply_zones_runtime(source_id, detector_zones)
    apply_meta = _runtime_apply_result(name, applied)
    return {
        "zones": ui_zones,
        "status": "updated",
        **apply_meta,
    }


@router.get("/{name}/zone-detector-params")
async def get_zone_detector_params(name: str) -> dict:
    body = _load(name)
    return zone_detector_params(body)


@router.put("/{name}/zone-detector-params")
async def put_zone_detector_params(name: str, payload: ZoneDetectorParamsUpdate) -> dict:
    body = _load(name)
    set_zone_detector_params(
        body,
        event_threshold=payload.event_threshold,
        zone_left_threshold=payload.zone_left_threshold,
    )
    _save(name, body)
    applied = False
    if _find_runtime_id_for_config(name) is not None:
        applied = _apply_zone_detector_params_runtime(
            payload.event_threshold,
            payload.zone_left_threshold,
        )
    apply_meta = _runtime_apply_result(name, applied)
    return {
        "status": "updated",
        **zone_detector_params(body),
        **apply_meta,
    }


@router.get("/{name}/schedule-alarm")
async def get_schedule_alarm_global(name: str) -> dict:
    body = _load(name)
    return get_global_schedule_alarm_params(body)


@router.put("/{name}/schedule-alarm")
async def put_schedule_alarm_global(name: str, payload: ScheduleAlarmGlobalUpdate) -> dict:
    body = _load(name)
    set_global_schedule_alarm_params(
        body,
        camera_cooldown_sec=payload.camera_cooldown_sec,
        default_schedule=payload.default_schedule.model_dump(),
    )
    errors = validate_schedule_alarm_section(schedule_alarm_detector_section(body))
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    _save(name, body)
    applied = False
    if _find_runtime_id_for_config(name) is not None:
        applied = _apply_schedule_alarm_runtime(
            "global",
            params={
                "camera_cooldown_sec": payload.camera_cooldown_sec,
                "default_schedule": payload.default_schedule.model_dump(),
            },
        )
    apply_meta = _runtime_apply_result(name, applied)
    return {
        "status": "updated",
        **get_global_schedule_alarm_params(body),
        **apply_meta,
    }


@router.get("/{name}/sources/{source_id}/schedule-alarm")
async def get_source_schedule_alarm(name: str, source_id: int) -> dict:
    body = _load(name)
    return {
        "schedule": get_effective_source_schedule(body, source_id),
        "has_override": source_has_override(body, source_id),
    }


@router.put("/{name}/sources/{source_id}/schedule-alarm")
async def put_source_schedule_alarm(
    name: str,
    source_id: int,
    payload: ScheduleAlarmSourceUpdate,
) -> dict:
    body = _load(name)
    schedule = payload.schedule.model_dump() if payload.schedule is not None else None
    set_source_schedule_override(body, source_id, schedule)
    errors = validate_schedule_alarm_section(schedule_alarm_detector_section(body))
    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))
    _save(name, body)
    applied = False
    if _find_runtime_id_for_config(name) is not None:
        applied = _apply_schedule_alarm_runtime(
            "source",
            source_id=int(source_id),
            schedule=schedule,
        )
    apply_meta = _runtime_apply_result(name, applied)
    return {
        "status": "updated",
        "schedule": get_effective_source_schedule(body, source_id),
        "has_override": source_has_override(body, source_id),
        **apply_meta,
    }


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
