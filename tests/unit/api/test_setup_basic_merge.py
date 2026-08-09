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


def test_recording_enabled_follows_source_record_flags():
    basic = {
        "data_dir": "D",
        "storage_mode": "json",
        "sources": [
            {"id": 0, "name": "Cam1", "type": "VideoFile", "address": "a.mp4", "record": True},
            {"id": 1, "name": "Cam2", "type": "VideoFile", "address": "b.mp4", "record": False},
        ],
        "analytics_enabled": False,
        "recording_enabled": False,  # ignored when sources present
    }
    cfg, _ = apply_basic_setup({}, basic, {})
    assert cfg["record"]["enabled"] is True
    assert cfg["record"]["enabled_sources"]["0"] is True
    assert cfg["record"]["enabled_sources"]["1"] is False


def test_recording_disabled_when_all_sources_off():
    basic = {
        "data_dir": "D",
        "storage_mode": "json",
        "sources": [
            {"id": 0, "name": "Cam1", "type": "VideoFile", "address": "a.mp4", "record": False},
        ],
        "analytics_enabled": False,
        "recording_enabled": True,  # ignored when sources present
    }
    cfg, _ = apply_basic_setup({}, basic, {})
    assert cfg["record"]["enabled"] is False
    assert cfg["record"]["enabled_sources"]["0"] is False


def test_project_recording_enabled_follows_enabled_sources_dict():
    cfg = _rich_config()
    cfg["record"] = {"enabled": True, "enabled_sources": {"0": True}}
    projected = project_basic_from_config(cfg, {}, config_name="system.json")
    assert projected["sources"][0]["record"] is True
    assert projected["recording_enabled"] is True


def test_project_recording_off_when_master_disabled():
    cfg = _rich_config()
    cfg["record"] = {"enabled": False, "enabled_sources": {"0": True}}
    projected = project_basic_from_config(cfg, {}, config_name="system.json")
    assert projected["sources"][0]["record"] is False
    assert projected["recording_enabled"] is False


def test_project_empty_enabled_sources_list_follows_master():
    cfg = _rich_config()
    cfg["record"] = {"enabled": True, "enabled_sources": []}
    projected = project_basic_from_config(cfg, {}, config_name="system.json")
    assert projected["sources"][0]["record"] is True
    assert projected["recording_enabled"] is True


def test_project_dict_all_false_means_recording_off():
    cfg = _rich_config()
    cfg["record"] = {"enabled": True, "enabled_sources": {"0": False}}
    projected = project_basic_from_config(cfg, {}, config_name="system.json")
    assert projected["sources"][0]["record"] is False
    assert projected["recording_enabled"] is False


def _poly_like_config():
    return {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://a",
                    "source_ids": [0],
                    "source_names": ["Cam1"],
                    "split": False,
                    "gstreamer_pipeline": "keep-me",
                },
                {
                    "source": "IpCamera",
                    "camera": "rtsp://b",
                    "source_ids": [1, 2],
                    "source_names": ["Cam2", "Cam3"],
                    "split": True,
                    "gstreamer_pipeline": "split-pipe",
                    "roi": [[0, 0], [1, 1]],
                },
                {
                    "source": "IpCamera",
                    "camera": "rtsp://c",
                    "source_ids": [3, 4],
                    "source_names": ["Cam4", "Cam5"],
                    "split": True,
                },
            ],
            "detectors": [
                {
                    "source_ids": [0],
                    "model": "models/yolov8n.pt",
                    "type": "ObjectDetectorYolo",
                    "mp_restart_on_exit": True,
                    "mp_no_restart_exit_codes": [-15],
                },
                {
                    "source_ids": [1],
                    "model": "models/yolov8n.pt",
                    "type": "ObjectDetectorYolo",
                    "mp_restart_on_exit": True,
                },
            ],
            "trackers": [
                {
                    "source_ids": [0],
                    "tracker_config": {"tracker_type": "botsort"},
                    "type": "ObjectTrackingBotsort",
                    "execution_mode": "process",
                    "mp_restart_on_exit": True,
                }
            ],
            "mc_trackers": [{"source_ids": [0, 1, 2, 3, 4], "enable": False}],
        },
        "controller": {"use_database": False, "fps": 30, "gui_enabled": False},
        "database": {"image_dir": "EvilEyeData", "preview_width": 300, "preview_height": 150},
        "record": {
            "enabled": True,
            "continuous_recording_enabled": True,
            "event_recording_enabled": True,
            "enabled_sources": [],
            "container": "mp4",
            "retention_days": 7,
            "out_dir": "EvilEyeData",
        },
        "events_detectors": {"ZoneEventsDetector": {"sources": {"0": True}}},
        "events_processor": {"keep": True},
        "objects_handler": {"max_active_objects": 50},
        "visualizer": {"num_width": 2, "num_height": 2},
        "server": {"enabled": True, "port": 8181},
    }


def test_split_sources_preserved_on_basic_roundtrip():
    original = _poly_like_config()
    basic = project_basic_from_config(original, {}, config_name="poly.json")
    assert len(basic["sources"]) == 3
    assert basic["sources"][1]["extra_names"] == ["Cam3"]
    # Disable recording only
    for s in basic["sources"]:
        s["record"] = False
    cfg, _ = apply_basic_setup(original, basic, {})

    assert cfg["pipeline"]["sources"][1]["source_ids"] == [1, 2]
    assert cfg["pipeline"]["sources"][1]["source_names"] == ["Cam2", "Cam3"]
    assert cfg["pipeline"]["sources"][1]["split"] is True
    assert cfg["pipeline"]["sources"][1]["gstreamer_pipeline"] == "split-pipe"
    assert cfg["pipeline"]["sources"][2]["source_ids"] == [3, 4]
    assert cfg["pipeline"]["sources"][2]["source_names"] == ["Cam4", "Cam5"]

    assert cfg["record"]["enabled"] is False
    assert cfg["record"]["enabled_sources"] == {
        "0": False,
        "1": False,
        "2": False,
        "3": False,
        "4": False,
    }
    assert cfg["record"]["container"] == "mp4"
    assert cfg["record"]["retention_days"] == 7
    assert cfg["record"]["continuous_recording_enabled"] is True

    # Unmanaged sections untouched
    assert cfg["pipeline"]["detectors"][0]["type"] == "ObjectDetectorYolo"
    assert cfg["pipeline"]["detectors"][0]["mp_restart_on_exit"] is True
    assert cfg["pipeline"]["detectors"][0]["mp_no_restart_exit_codes"] == [-15]
    assert cfg["pipeline"]["trackers"][0]["type"] == "ObjectTrackingBotsort"
    assert cfg["pipeline"]["trackers"][0]["execution_mode"] == "process"
    assert cfg["pipeline"]["mc_trackers"] == original["pipeline"]["mc_trackers"]
    assert cfg["events_detectors"] == original["events_detectors"]
    assert cfg["events_processor"] == original["events_processor"]
    assert cfg["objects_handler"] == original["objects_handler"]
    assert cfg["visualizer"] == original["visualizer"]
    assert cfg["server"] == original["server"]
    assert cfg["controller"]["fps"] == 30
    assert cfg["controller"]["gui_enabled"] is False


def test_does_not_overwrite_existing_pipeline_class():
    rich = _rich_config()
    rich["pipeline"]["pipeline_class"] = "CustomPipeline"
    basic = project_basic_from_config(rich, {})
    cfg, _ = apply_basic_setup(rich, basic, {})
    assert cfg["pipeline"]["pipeline_class"] == "CustomPipeline"
