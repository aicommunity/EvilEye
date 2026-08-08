from evileye.api.core.setup_basic_merge import apply_basic_setup, project_basic_from_config


def _rich_config():
    return {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://cam/1",
                    "source_ids": [0],
                    "source_names": ["Front"],
                    "roi": [[0, 0], [10, 10]],
                    "zones": {"A": [[1, 1], [2, 2]]},
                    "split": False,
                    "custom_meta": {"keep": True},
                }
            ],
            "detectors": [{"source_ids": [0], "model_path": "models/custom.pt", "conf": 0.4}],
            "trackers": [{"source_ids": [0], "max_age": 40}],
            "mc_trackers": [{"source_ids": [0], "enable": False}],
        },
        "controller": {"use_database": False, "fps": 25, "gui_enabled": False},
        "database": {"image_dir": "OldData", "preview_width": 300},
        "record": {"enabled": False, "out_dir": "CustomRecord"},
        "events_detectors": {"ZoneEventsDetector": {"sources": {"0": True}}},
        "objects_handler": {"max_active_objects": 50},
        "visualizer": {"num_width": 2},
    }


def test_merge_preserves_roi_zones_and_detector_params():
    basic = {
        "data_dir": "EvilEyeData",
        "storage_mode": "json",
        "database": {},
        "sources": [
            {
                "id": 0,
                "name": "Front",
                "type": "IpCamera",
                "address": "rtsp://cam/1",
                "record": True,
            }
        ],
        "analytics_enabled": True,
        "recording_enabled": True,
    }
    cfg, _creds = apply_basic_setup(_rich_config(), basic, {})
    src = cfg["pipeline"]["sources"][0]
    assert src["roi"] == [[0, 0], [10, 10]]
    assert src["zones"] == {"A": [[1, 1], [2, 2]]}
    assert src["custom_meta"] == {"keep": True}
    assert cfg["pipeline"]["detectors"][0]["model_path"] == "models/custom.pt"
    assert cfg["pipeline"]["detectors"][0]["conf"] == 0.4
    assert cfg["events_detectors"]["ZoneEventsDetector"]["sources"]["0"] is True
    assert cfg["objects_handler"]["max_active_objects"] == 50
    assert cfg["record"]["out_dir"] == "CustomRecord"  # custom out_dir preserved
    assert cfg["database"]["image_dir"] == "EvilEyeData"
    assert cfg["record"]["enabled"] is True


def test_analytics_off_clears_detectors_trackers_only():
    basic = {
        "data_dir": "D",
        "storage_mode": "json",
        "sources": [{"id": 0, "name": "Cam1", "type": "VideoFile", "address": "a.mp4"}],
        "analytics_enabled": False,
        "recording_enabled": False,
    }
    cfg, _ = apply_basic_setup(_rich_config(), basic, {})
    assert cfg["pipeline"]["detectors"] == []
    assert cfg["pipeline"]["trackers"] == []
    assert cfg["events_detectors"]  # preserved
    assert cfg["pipeline"]["mc_trackers"]  # preserved


def test_analytics_on_does_not_wipe_model_path():
    basic = {
        "data_dir": "D",
        "storage_mode": "json",
        "sources": [{"id": 0, "name": "Front", "type": "IpCamera", "address": "rtsp://cam/1"}],
        "analytics_enabled": True,
        "recording_enabled": False,
    }
    cfg, _ = apply_basic_setup(_rich_config(), basic, {})
    assert cfg["pipeline"]["detectors"][0]["model_path"] == "models/custom.pt"


def test_storage_json_sets_use_database_false():
    basic = {
        "data_dir": "D",
        "storage_mode": "json",
        "sources": [],
        "analytics_enabled": False,
        "recording_enabled": False,
    }
    rich = _rich_config()
    rich["controller"]["use_database"] = True
    cfg, _ = apply_basic_setup(rich, basic, {})
    assert cfg["controller"]["use_database"] is False


def test_project_basic_roundtrip_fields():
    cfg = _rich_config()
    projected = project_basic_from_config(cfg, {}, config_name="system.json")
    assert projected["config_name"] == "system.json"
    assert projected["sources"][0]["name"] == "Front"
    assert projected["analytics_enabled"] is True
