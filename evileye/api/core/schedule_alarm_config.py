"""Schedule alarm configuration helpers shared by API editors and runtime control."""

from __future__ import annotations

from typing import Any

from evileye.events_detectors.schedule_alarm_logic import (
    DETECTOR_CONFIG_KEY,
    DetectorScheduleConfig,
    effective_schedule_for_source,
    normalize_schedule_dict,
    parse_detector_params,
    schedule_to_json,
    detector_params_to_json,
    resolve_detector_section,
)


def schedule_alarm_detector_section(body: dict[str, Any]) -> dict[str, Any]:
    events = body.get("events_detectors") or {}
    if not isinstance(events, dict):
        return {}
    return resolve_detector_section(events)


def get_global_schedule_alarm_params(body: dict[str, Any]) -> dict[str, Any]:
    cfg = parse_detector_params(schedule_alarm_detector_section(body))
    return {
        "camera_cooldown_sec": int(cfg.camera_cooldown_sec),
        "default_schedule": schedule_to_json(cfg.default_schedule),
    }


def get_effective_source_schedule(body: dict[str, Any], source_id: int) -> dict[str, Any]:
    cfg = parse_detector_params(schedule_alarm_detector_section(body))
    return schedule_to_json(effective_schedule_for_source(cfg, int(source_id)))


def source_has_override(body: dict[str, Any], source_id: int) -> bool:
    section = schedule_alarm_detector_section(body)
    sources = section.get("sources") or {}
    if not isinstance(sources, dict):
        return False
    return str(source_id) in sources or int(source_id) in sources


def set_global_schedule_alarm_params(
    body: dict[str, Any],
    *,
    camera_cooldown_sec: int,
    default_schedule: dict[str, Any],
) -> None:
    events = body.setdefault("events_detectors", {})
    if not isinstance(events, dict):
        body["events_detectors"] = {}
        events = body["events_detectors"]
    section = events.setdefault(DETECTOR_CONFIG_KEY, {})
    if not isinstance(section, dict):
        section = {}
        events[DETECTOR_CONFIG_KEY] = section
    section["camera_cooldown_sec"] = max(0, int(camera_cooldown_sec))
    section["default_schedule"] = schedule_to_json(
        normalize_schedule_dict(default_schedule, default_enabled=True)
    )


def set_source_schedule_override(
    body: dict[str, Any],
    source_id: int,
    schedule: dict[str, Any] | None,
) -> None:
    events = body.setdefault("events_detectors", {})
    if not isinstance(events, dict):
        body["events_detectors"] = {}
        events = body["events_detectors"]
    section = events.setdefault(DETECTOR_CONFIG_KEY, {})
    if not isinstance(section, dict):
        section = {}
        events[DETECTOR_CONFIG_KEY] = section
    sources = section.setdefault("sources", {})
    if not isinstance(sources, dict):
        sources = {}
        section["sources"] = sources
    key = str(int(source_id))
    if schedule is None:
        sources.pop(key, None)
    else:
        sources[key] = schedule_to_json(normalize_schedule_dict(schedule, default_enabled=True))


def validate_schedule_alarm_section(section: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not isinstance(section, dict):
        return ["schedule alarm section must be an object"]
    cfg: DetectorScheduleConfig = parse_detector_params(section)

    def _validate_schedule(name: str, schedule) -> None:
        for day in schedule.weekdays:
            if day < 0 or day > 6:
                errors.append(f"{name}: invalid weekday {day}")
        if schedule.enabled and not schedule.periods:
            errors.append(f"{name}: enabled schedule requires at least one period")

    _validate_schedule("default_schedule", cfg.default_schedule)
    for source_id, schedule in cfg.sources.items():
        _validate_schedule(f"sources[{source_id}]", schedule)

    if cfg.camera_cooldown_sec < 0:
        errors.append("camera_cooldown_sec must be >= 0")
    return errors
