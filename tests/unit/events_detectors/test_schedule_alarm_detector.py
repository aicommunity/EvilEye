from unittest.mock import MagicMock

from evileye.events_detectors.schedule_alarm_events_detector import ScheduleAlarmEventsDetector
from evileye.events_detectors.schedule_alarm_logic import infer_active_source_ids, parse_detector_params


def test_infer_active_source_ids_respects_disabled_cameras():
    cfg = parse_detector_params(
        {
            "default_schedule": {
                "enabled": True,
                "weekdays": [0, 1, 2, 3, 4, 5, 6],
                "periods": [["22:00:00", "06:00:00"]],
                "class_ids": [],
            },
            "sources": {
                "1": {"enabled": False, "weekdays": [], "periods": [], "class_ids": []},
            },
        }
    )
    ids = infer_active_source_ids(cfg, pipeline_source_ids=[0, 1, 2])
    assert ids == {0, 2}


def test_detector_skips_disabled_camera():
    handler = MagicMock()
    detector = ScheduleAlarmEventsDetector(handler, pipeline_source_ids=[0, 1])
    detector.set_params(
        **{
            "default_schedule": {
                "enabled": True,
                "weekdays": [0, 1, 2, 3, 4, 5, 6],
                "periods": [["00:00:00", "23:59:59"]],
                "class_ids": [],
            },
            "sources": {
                "1": {"enabled": False, "weekdays": [], "periods": [], "class_ids": []},
            },
            "camera_cooldown_sec": 0,
        }
    )
    detector.init()
    assert detector._source_ids == {0}
