import json
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from evileye.cli import (
    _parse_time_str,
    _get_next_daily_time,
    _get_next_interval,
    _load_scheduled_restart_config,
)
from evileye.core.logger import get_module_logger


def test_parse_time_str_valid():
    assert _parse_time_str("01:00") == (1, 0)
    assert _parse_time_str("23:59") == (23, 59)


@pytest.mark.parametrize("value", ["24:00", "12:60", "bad", "12", "12:"])
def test_parse_time_str_invalid(value):
    with pytest.raises(ValueError):
        _parse_time_str(value)


def test_get_next_daily_time_moves_to_next_day_if_past():
    now = datetime(2024, 1, 1, 2, 0, 0)
    # time earlier than now -> should go to next day
    next_time = _get_next_daily_time(now, "01:00")
    assert next_time.date() == (now + timedelta(days=1)).date()
    assert next_time.hour == 1 and next_time.minute == 0


def test_get_next_daily_time_same_day_if_future():
    now = datetime(2024, 1, 1, 0, 30, 0)
    next_time = _get_next_daily_time(now, "01:00")
    assert next_time.date() == now.date()
    assert next_time.hour == 1 and next_time.minute == 0


def test_get_next_interval_minimum_one_minute():
    now = datetime(2024, 1, 1, 0, 0, 0)
    next_time = _get_next_interval(now, 0)
    assert (next_time - now) == timedelta(minutes=1)


def test_load_scheduled_restart_defaults(tmp_path: Path):
    # config without scheduled_restart section -> should get defaults
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(json.dumps({"controller": {}}), encoding="utf-8")
    logger = get_module_logger("test_scheduled_restart")

    sched = _load_scheduled_restart_config(cfg_path, logger)
    assert sched["enabled"] is False
    assert sched["mode"] == "daily_time"
    assert sched["time"] == "01:00"
    assert sched["interval_minutes"] == 0


def test_load_scheduled_restart_overrides(tmp_path: Path):
    cfg_path = tmp_path / "config.json"
    cfg_path.write_text(
        json.dumps(
            {
                "controller": {
                    "scheduled_restart": {
                        "enabled": True,
                        "mode": "interval",
                        "time": "02:30",
                        "interval_minutes": 5,
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    logger = get_module_logger("test_scheduled_restart")

    sched = _load_scheduled_restart_config(cfg_path, logger)
    assert sched["enabled"] is True
    assert sched["mode"] == "interval"
    assert sched["time"] == "02:30"
    assert sched["interval_minutes"] == 5

