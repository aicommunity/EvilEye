from datetime import datetime, time

import pytest

from evileye.events_detectors.schedule_alarm_logic import (
    TimePeriod,
    SourceSchedule,
    is_time_in_period,
    is_in_schedule,
    normalize_schedule_dict,
    merge_source_schedule,
    parse_detector_params,
    resolve_detector_section,
    find_first_schedule_hit_in_history,
    matches_class,
    LEGACY_DETECTOR_CONFIG_KEY,
    DETECTOR_CONFIG_KEY,
)


class _Hist:
    def __init__(self, ts: datetime):
        self.time_stamp = ts


class _Obj:
    def __init__(self, class_id=None):
        self.class_id = class_id


def test_overnight_period():
    period = TimePeriod(time(22, 0), time(6, 0))
    assert is_time_in_period(time(23, 0), period)
    assert is_time_in_period(time(3, 0), period)
    assert not is_time_in_period(time(12, 0), period)


def test_weekday_filter():
    schedule = SourceSchedule(
        enabled=True,
        weekdays=frozenset({0}),
        periods=(TimePeriod(time(0, 0), time(23, 59, 59)),),
    )
    monday = datetime(2026, 3, 2, 10, 0, 0)
    sunday = datetime(2026, 3, 1, 10, 0, 0)
    assert is_in_schedule(monday, schedule)
    assert not is_in_schedule(sunday, schedule)


def test_legacy_list_parse():
    schedule = normalize_schedule_dict([["22:00:00", "06:00:00"]])
    assert schedule.enabled
    assert len(schedule.periods) == 1


def test_merge_override():
    default = SourceSchedule(enabled=True, weekdays=frozenset({0, 1, 2, 3, 4}))
    override = SourceSchedule(enabled=True, weekdays=frozenset({6}))
    merged = merge_source_schedule(default, override)
    assert merged.weekdays == frozenset({6})


def test_matches_class_filter():
    assert matches_class(_Obj(1), frozenset())
    assert matches_class(_Obj(1), frozenset({1}))
    assert not matches_class(_Obj(0), frozenset({1}))
    assert not matches_class(_Obj(None), frozenset({1}))


def test_resolve_legacy_section():
    section = resolve_detector_section({LEGACY_DETECTOR_CONFIG_KEY: {"sources": {}}})
    assert section == {"sources": {}}


def test_find_first_schedule_hit():
    schedule = normalize_schedule_dict([["00:00:00", "23:59:59"]])
    history = [_Hist(datetime(2026, 3, 2, 12, 0, 0))]
    assert find_first_schedule_hit_in_history(history, schedule) == 0


def test_parse_detector_params_with_default():
    cfg = parse_detector_params(
        {
            "camera_cooldown_sec": 30,
            "default_schedule": {"enabled": True, "periods": [["22:00:00", "06:00:00"]]},
        }
    )
    assert cfg.camera_cooldown_sec == 30
    assert cfg.default_schedule.enabled
