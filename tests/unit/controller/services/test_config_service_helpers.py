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
