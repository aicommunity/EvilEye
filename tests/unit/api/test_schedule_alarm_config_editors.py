import json
from pathlib import Path

from evileye.api.core.schedule_alarm_config import (
    get_global_schedule_alarm_params,
    set_global_schedule_alarm_params,
    set_source_schedule_override,
    get_effective_source_schedule,
)
from evileye.events_detectors.schedule_alarm_logic import DETECTOR_CONFIG_KEY


def test_global_and_source_schedule_roundtrip():
    body: dict = {"events_detectors": {}}
    set_global_schedule_alarm_params(
        body,
        camera_cooldown_sec=45,
        default_schedule={
            "enabled": True,
            "weekdays": [0, 1, 2, 3, 4],
            "periods": [["22:00:00", "06:00:00"]],
            "class_ids": [],
        },
    )
    set_source_schedule_override(
        body,
        1,
        {
            "enabled": True,
            "weekdays": [6],
            "periods": [["12:00:00", "13:00:00"]],
            "class_ids": [0],
        },
    )
    global_params = get_global_schedule_alarm_params(body)
    assert global_params["camera_cooldown_sec"] == 45
    effective = get_effective_source_schedule(body, 1)
    assert effective["weekdays"] == [6]
    assert DETECTOR_CONFIG_KEY in body["events_detectors"]
