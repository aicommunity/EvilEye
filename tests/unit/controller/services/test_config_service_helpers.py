from evileye.controller.services.config_service import ConfigurationService


def test_apply_save_sanitizers_strips_injected_password():
    svc = ConfigurationService()
    loaded = {"pipeline": {"sources": [{"camera": "rtsp://x"}]}, "database": {"image_dir": "d"}}
    params = {
        "pipeline": {"sources": [{"camera": "rtsp://x", "password": "x"}]},
        "database": {"image_dir": "d", "extra": "drop"},
    }
    svc.apply_save_sanitizers(params, loaded, credentials_loaded=False)
    assert "password" not in params["pipeline"]["sources"][0]
    assert "extra" not in params["database"]


def test_propagate_record_config_sets_out_dir():
    svc = ConfigurationService()
    pipeline_params = {"sources": [{"source_ids": [0], "source_names": ["cam0"]}]}
    params = {"record": {"enabled": True}, "database": {"image_dir": "EvilEyeData"}}
    svc.propagate_record_config_to_sources(pipeline_params, params)
    record = pipeline_params["sources"][0]["record"]
    assert record["out_dir"]
    assert record.get("continuous_recording_enabled") is True


def test_propagate_record_respects_enabled_sources_dict():
    svc = ConfigurationService()
    pipeline_params = {
        "sources": [
            {"source_ids": [0], "source_names": ["Cam1"]},
            {"source_ids": [1], "source_names": ["Cam2"]},
        ]
    }
    params = {
        "record": {
            "enabled": True,
            "continuous_recording_enabled": True,
            "enabled_sources": {"0": True, "1": False},
        },
        "database": {"image_dir": "EvilEyeData"},
    }
    svc.propagate_record_config_to_sources(pipeline_params, params)
    assert pipeline_params["sources"][0]["record"]["enabled"] is True
    assert pipeline_params["sources"][1]["record"]["enabled"] is False


def test_propagate_record_empty_list_keeps_master_enabled():
    svc = ConfigurationService()
    pipeline_params = {"sources": [{"source_ids": [0], "source_names": ["Cam1"]}]}
    params = {
        "record": {
            "enabled": True,
            "continuous_recording_enabled": True,
            "event_recording_enabled": True,
            "enabled_sources": [],
        },
        "database": {"image_dir": "EvilEyeData"},
    }
    svc.propagate_record_config_to_sources(pipeline_params, params)
    assert pipeline_params["sources"][0]["record"]["enabled"] is True


def test_propagate_record_disables_when_out_dir_unwritable(tmp_path):
    svc = ConfigurationService()
    blocker = tmp_path / "not_a_dir"
    blocker.write_text("x", encoding="utf-8")
    bad_out = str(blocker / "streams")
    pipeline_params = {
        "sources": [
            {
                "source_ids": [0],
                "source_names": ["cam0"],
                "record": {
                    "enabled": True,
                    "continuous_recording_enabled": True,
                    "event_recording_enabled": True,
                    "out_dir": bad_out,
                },
            }
        ]
    }
    params = {
        "record": {
            "enabled": True,
            "continuous_recording_enabled": True,
            "event_recording_enabled": True,
            "allow_custom_out_dir": True,
        },
        "database": {"image_dir": "EvilEyeData"},
    }
    svc.propagate_record_config_to_sources(pipeline_params, params)
    record = pipeline_params["sources"][0]["record"]
    assert record.get("enabled") is False
    assert record.get("continuous_recording_enabled") is False
    assert record.get("event_recording_enabled") is False
