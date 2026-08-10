from evileye.api.core.setup_basic_merge import (
    config_needs_setup,
    project_basic_from_config,
    resolve_usable_data_dir,
)
from evileye.api.routes.setup import _build_status
from evileye.service_manager.minimal_config import minimal_system_config


def test_poly_like_config_does_not_need_setup():
    cfg = {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://cam/1",
                    "source_ids": [0],
                    "source_names": ["Cam1"],
                    "out_dir": "/home/user/EvilEye/EvilEyeData",
                }
            ],
            "detectors": [{"source_ids": [0]}],
            "trackers": [{"source_ids": [0]}],
        },
        "controller": {"use_database": False},
        "database": {},
        "record": {"enabled": True},
    }
    assert config_needs_setup(cfg) is False
    assert resolve_usable_data_dir(cfg) == "/home/user/EvilEye/EvilEyeData"


def test_system_scaffold_needs_setup():
    assert config_needs_setup(minimal_system_config()) is True
    assert resolve_usable_data_dir(minimal_system_config()) == ""


def test_project_basic_uses_source_out_dir_fallback():
    cfg = {
        "pipeline": {
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://x",
                    "source_ids": [0],
                    "source_names": ["A"],
                    "out_dir": "/data/from/source",
                }
            ],
            "detectors": [],
            "trackers": [],
        },
        "controller": {"use_database": False},
        "database": {},
        "record": {},
    }
    projected = project_basic_from_config(cfg, {}, config_name="poly-cameras-gst.json")
    assert projected["data_dir"] == "/data/from/source"
    assert projected["sources"][0]["name"] == "A"


def test_build_status_respects_config_query(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    configs = tmp_path / "configs"
    configs.mkdir()
    import json

    (tmp_path / "credentials.json").write_text(
        json.dumps({"web_auth": {"enabled": False, "users": []}, "setup": {"default_config": "system.json"}}),
        encoding="utf-8",
    )
    (configs / "system.json").write_text(json.dumps(minimal_system_config()), encoding="utf-8")
    poly = {
        "pipeline": {
            "pipeline_class": "PipelineSurveillance",
            "sources": [
                {
                    "source": "IpCamera",
                    "camera": "rtsp://cam",
                    "source_ids": [0],
                    "source_names": ["Cam1"],
                    "out_dir": "/tmp/data",
                }
            ],
            "detectors": [{"source_ids": [0]}],
            "trackers": [],
        },
        "controller": {"use_database": False},
        "database": {},
        "record": {},
    }
    (configs / "poly-cameras-gst.json").write_text(json.dumps(poly), encoding="utf-8")

    default_status = _build_status()
    assert default_status["needs_setup"] is True

    poly_status = _build_status(config_name="poly-cameras-gst.json")
    assert poly_status["needs_setup"] is False
    assert poly_status["has_sources"] is True
    assert poly_status["data_dir"] == "/tmp/data"
