import json
from pathlib import Path

import pytest

from evileye.capture.video_capture_opencv import VideoCaptureOpencv
from evileye.controller.services.config_service import ConfigurationService
from evileye.core.processor_base import EXEC_MODE_PROCESS


@pytest.mark.unit
def test_worker_capture_params_include_record_after_propagate():
    repo_root = Path(__file__).resolve().parents[3]
    cfg = json.loads((repo_root / "configs" / "poly-cameras.json").read_text())
    pipeline = cfg["pipeline"]
    ConfigurationService().propagate_record_config_to_sources(pipeline, cfg)

    cap = VideoCaptureOpencv()
    cap.set_params(**pipeline["sources"][0])
    worker_params = cap._worker_capture_params()

    record = worker_params.get("record") or {}
    assert record.get("enabled") is True
    assert record.get("continuous_recording_enabled") is True
    assert record.get("out_dir") == "/media/user/Data8/EvilEyeData"


@pytest.mark.unit
def test_get_params_impl_roundtrips_record():
    cap = VideoCaptureOpencv()
    cap.set_params(
        source="VideoFile",
        camera="x.mp4",
        source_ids=[0],
        source_names=["Cam1"],
        execution_mode=EXEC_MODE_PROCESS,
        record={
            "enabled": True,
            "continuous_recording_enabled": True,
            "out_dir": "/tmp/evileye-test",
        },
    )
    params = cap.get_params()
    assert params["record"]["continuous_recording_enabled"] is True
    assert params["record"]["out_dir"] == "/tmp/evileye-test"
