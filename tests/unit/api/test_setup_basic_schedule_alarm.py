from evileye.api.core.setup_basic_merge import apply_basic_setup, project_basic_from_config


def test_basic_alarm_schedule_roundtrip():
    config = {
        "pipeline": {
            "sources": [
                {"source_ids": [0], "source_names": ["Cam1"], "camera": "rtsp://x"},
                {
                    "source_ids": [1, 2],
                    "source_names": ["Cam2", "Cam3"],
                    "split": True,
                    "camera": "rtsp://y",
                },
            ]
        },
        "controller": {"use_database": False},
        "events_detectors": {
            "ScheduleAlarmEventsDetector": {
                "camera_cooldown_sec": 10,
                "default_schedule": {
                    "enabled": True,
                    "weekdays": [0, 1, 2, 3, 4, 5, 6],
                    "periods": [["22:00:00", "06:00:00"]],
                    "class_ids": [],
                },
                "sources": {
                    "0": {
                        "enabled": True,
                        "weekdays": [0],
                        "periods": [["01:00:00", "02:00:00"]],
                        "class_ids": [],
                    },
                    "2": {
                        "enabled": False,
                        "weekdays": [],
                        "periods": [],
                        "class_ids": [],
                    },
                },
            }
        },
    }
    basic = project_basic_from_config(config, config_name="test.json")
    assert basic["alarm_schedule"]["enabled"] is True
    assert [c["id"] for c in basic["alarm_cameras"]] == [0, 1, 2]
    assert basic["alarm_cameras"][0]["alarm_schedule"]["weekdays"] == [0]
    assert basic["alarm_cameras"][0]["alarm_enabled"] is True
    assert basic["alarm_cameras"][1]["alarm_enabled"] is True
    assert basic["alarm_cameras"][2]["alarm_enabled"] is False
    assert basic["sources"][1]["logical_ids"] == [1, 2]

    merged, _ = apply_basic_setup(
        config,
        {
            "data_dir": "EvilEyeData",
            "storage_mode": "json",
            "analytics_enabled": False,
            "recording_enabled": False,
            "sources": basic["sources"],
            "alarm_schedule": {**basic["alarm_schedule"], "camera_cooldown_sec": 10},
            "alarm_cameras": basic["alarm_cameras"],
        },
    )
    section = merged["events_detectors"]["ScheduleAlarmEventsDetector"]
    assert section["camera_cooldown_sec"] == 10
    assert section["sources"]["0"]["weekdays"] == [0]
    assert section["sources"]["2"]["enabled"] is False
    assert "1" not in section["sources"]
