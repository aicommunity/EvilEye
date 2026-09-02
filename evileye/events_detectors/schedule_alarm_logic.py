"""Schedule alarm detector configuration and time-window logic."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, time
from typing import Any

_logger = logging.getLogger(__name__)

DETECTOR_CONFIG_KEY = "ScheduleAlarmEventsDetector"
LEGACY_DETECTOR_CONFIG_KEY = "FieldOfViewEventsDetector"

ALL_WEEKDAYS = frozenset(range(7))


@dataclass(frozen=True)
class TimePeriod:
    start: time
    end: time


@dataclass(frozen=True)
class SourceSchedule:
    enabled: bool = True
    weekdays: frozenset[int] = ALL_WEEKDAYS
    periods: tuple[TimePeriod, ...] = ()
    class_ids: frozenset[int] = frozenset()


@dataclass
class DetectorScheduleConfig:
    camera_cooldown_sec: int = 0
    default_schedule: SourceSchedule = field(default_factory=lambda: SourceSchedule(enabled=False))
    sources: dict[int, SourceSchedule] = field(default_factory=dict)


def parse_time_str(value: str) -> time:
    text = str(value or "").strip()
    for fmt in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"invalid time: {value!r}")


def is_time_in_period(t: time, period: TimePeriod) -> bool:
    start = period.start
    end = period.end
    if start == end:
        return False
    if start < end:
        return start <= t < end
    return t >= start or t < end


def is_in_schedule(dt: datetime, schedule: SourceSchedule) -> bool:
    if not schedule.enabled:
        return False
    if schedule.weekdays and dt.weekday() not in schedule.weekdays:
        return False
    if not schedule.periods:
        return False
    t = dt.time()
    return any(is_time_in_period(t, period) for period in schedule.periods)


def matches_class(obj: Any, class_ids: frozenset[int]) -> bool:
    if not class_ids:
        return True
    class_id = getattr(obj, "class_id", None)
    if class_id is None:
        return False
    try:
        return int(class_id) in class_ids
    except (TypeError, ValueError):
        return False


def _parse_periods(raw_periods: Any) -> tuple[TimePeriod, ...]:
    periods: list[TimePeriod] = []
    if not isinstance(raw_periods, list):
        return tuple()
    for item in raw_periods:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        try:
            periods.append(TimePeriod(parse_time_str(item[0]), parse_time_str(item[1])))
        except ValueError:
            continue
    return tuple(periods)


def _parse_weekdays(raw: Any) -> frozenset[int]:
    if not isinstance(raw, list):
        return ALL_WEEKDAYS
    out: set[int] = set()
    for item in raw:
        try:
            day = int(item)
        except (TypeError, ValueError):
            continue
        if 0 <= day <= 6:
            out.add(day)
    return frozenset(out) if out else ALL_WEEKDAYS


def _parse_class_ids(raw: Any) -> frozenset[int]:
    if not isinstance(raw, list):
        return frozenset()
    out: set[int] = set()
    for item in raw:
        try:
            cid = int(item)
        except (TypeError, ValueError):
            continue
        if cid >= 0:
            out.add(cid)
    return frozenset(out)


def normalize_schedule_dict(raw: Any, *, default_enabled: bool = True) -> SourceSchedule:
    if raw is None:
        return SourceSchedule(enabled=False)
    if isinstance(raw, list):
        periods = _parse_periods(raw)
        return SourceSchedule(
            enabled=default_enabled and bool(periods),
            weekdays=ALL_WEEKDAYS,
            periods=periods,
            class_ids=frozenset(),
        )
    if not isinstance(raw, dict):
        return SourceSchedule(enabled=False)
    enabled = bool(raw.get("enabled", default_enabled))
    return SourceSchedule(
        enabled=enabled,
        weekdays=_parse_weekdays(raw.get("weekdays")),
        periods=_parse_periods(raw.get("periods")),
        class_ids=_parse_class_ids(raw.get("class_ids")),
    )


def merge_source_schedule(
    default: SourceSchedule,
    override: SourceSchedule | None,
) -> SourceSchedule:
    if override is None:
        return default
    return SourceSchedule(
        enabled=override.enabled,
        weekdays=override.weekdays if override.weekdays else default.weekdays,
        periods=override.periods if override.periods else default.periods,
        class_ids=override.class_ids if override.class_ids else default.class_ids,
    )


def resolve_detector_section(events_detectors: dict | None) -> dict:
    events = events_detectors if isinstance(events_detectors, dict) else {}
    if DETECTOR_CONFIG_KEY in events:
        section = events.get(DETECTOR_CONFIG_KEY)
        return section if isinstance(section, dict) else {}
    if LEGACY_DETECTOR_CONFIG_KEY in events:
        _logger.warning(
            "%s is deprecated; use %s",
            LEGACY_DETECTOR_CONFIG_KEY,
            DETECTOR_CONFIG_KEY,
        )
        section = events.get(LEGACY_DETECTOR_CONFIG_KEY)
        return section if isinstance(section, dict) else {}
    return {}


def parse_detector_params(params: dict | None) -> DetectorScheduleConfig:
    raw = params if isinstance(params, dict) else {}
    default_schedule = normalize_schedule_dict(
        raw.get("default_schedule"),
        default_enabled=bool(raw.get("default_schedule")),
    )
    if "default_schedule" not in raw and raw.get("sources"):
        has_any_periods = any(
            isinstance(v, list) and v for v in raw.get("sources", {}).values()
        )
        if has_any_periods and not default_schedule.enabled:
            default_schedule = SourceSchedule(enabled=True, weekdays=ALL_WEEKDAYS)

    sources: dict[int, SourceSchedule] = {}
    raw_sources = raw.get("sources") or {}
    if isinstance(raw_sources, dict):
        for key, value in raw_sources.items():
            try:
                source_id = int(key)
            except (TypeError, ValueError):
                continue
            sources[source_id] = normalize_schedule_dict(value, default_enabled=True)

    cooldown = 0
    try:
        cooldown = max(0, int(raw.get("camera_cooldown_sec") or 0))
    except (TypeError, ValueError):
        cooldown = 0

    return DetectorScheduleConfig(
        camera_cooldown_sec=cooldown,
        default_schedule=default_schedule,
        sources=sources,
    )


def effective_schedule_for_source(cfg: DetectorScheduleConfig, source_id: int) -> SourceSchedule:
    override = cfg.sources.get(int(source_id))
    if override is None:
        return cfg.default_schedule
    return merge_source_schedule(cfg.default_schedule, override)


def schedule_to_json(schedule: SourceSchedule) -> dict:
    return {
        "enabled": bool(schedule.enabled),
        "weekdays": sorted(schedule.weekdays),
        "periods": [[p.start.strftime("%H:%M:%S"), p.end.strftime("%H:%M:%S")] for p in schedule.periods],
        "class_ids": sorted(schedule.class_ids),
    }


def detector_params_to_json(cfg: DetectorScheduleConfig) -> dict:
    sources_out: dict[str, dict] = {}
    for source_id, schedule in sorted(cfg.sources.items()):
        sources_out[str(source_id)] = schedule_to_json(schedule)
    return {
        "camera_cooldown_sec": int(cfg.camera_cooldown_sec),
        "default_schedule": schedule_to_json(cfg.default_schedule),
        "sources": sources_out,
    }


def find_first_schedule_hit_in_history(history: list, schedule: SourceSchedule) -> int:
    for idx, history_obj in enumerate(history or []):
        ts = getattr(history_obj, "time_stamp", None)
        if ts is None:
            continue
        if is_in_schedule(ts, schedule):
            return idx
    return -1


def infer_active_source_ids(cfg: DetectorScheduleConfig, pipeline_source_ids: list[int] | None = None) -> set[int]:
    ids: set[int] = set()
    pipeline_ids = [int(x) for x in (pipeline_source_ids or [])]

    if cfg.default_schedule.enabled and pipeline_ids:
        for sid in pipeline_ids:
            override = cfg.sources.get(sid)
            if override is None:
                ids.add(sid)
            elif override.enabled:
                ids.add(sid)

    for source_id, override in cfg.sources.items():
        sid = int(source_id)
        if sid in ids:
            continue
        effective = effective_schedule_for_source(cfg, sid)
        if effective.enabled:
            ids.add(sid)
    return ids
