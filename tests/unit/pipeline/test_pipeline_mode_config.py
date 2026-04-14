import json
from pathlib import Path

from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def test_pipeline_normalizes_ipc_mode_and_execution_mode():
    pipeline = PipelineSurveillance()
    src = {
        "pipeline_class": "PipelineSurveillance",
        "ipc_mode": "descriptor",
        "sources": [{"source_ids": [0]}],
        "detectors": [{"source_ids": [0], "execution_mode": "process"}],
        "trackers": [{"source_ids": [0]}],
    }

    normalized = pipeline._normalize_pipeline_params(src)

    assert normalized["ipc_mode"] == "descriptor"
    assert normalized["sources"][0]["execution_mode"] == "thread"
    assert normalized["sources"][0]["ipc_mode"] == "descriptor"
    assert normalized["detectors"][0]["execution_mode"] == "process"
    assert normalized["detectors"][0]["ipc_mode"] == "descriptor"
    assert normalized["trackers"][0]["execution_mode"] == "thread"


def test_pipeline_ipc_mode_defaults_to_standard():
    pipeline = PipelineSurveillance()
    src = {
        "pipeline_class": "PipelineSurveillance",
        "sources": [{"source_ids": [0]}],
    }
    normalized = pipeline._normalize_pipeline_params(src)
    assert normalized["ipc_mode"] == "standard"
    assert normalized["sources"][0]["ipc_mode"] == "standard"


def test_real_configs_current_execution_modes():
    repo_root = Path(__file__).resolve().parents[3]
    single_mp = json.loads((repo_root / "configs" / "single_video_multiprocess.json").read_text())
    poly = json.loads((repo_root / "configs" / "poly-videos-gst.json").read_text())

    assert single_mp["pipeline"]["sources"][0]["execution_mode"] == "process"
    assert single_mp["pipeline"]["detectors"][0]["execution_mode"] == "process"
    assert single_mp["pipeline"]["trackers"][0]["execution_mode"] == "process"
    assert single_mp["server"]["execution_mode"] == "process"

    assert poly["pipeline"]["detectors"][0]["execution_mode"] == "thread"
    assert "execution_mode" not in poly["pipeline"]["trackers"][0]
    assert poly["server"]["execution_mode"] == "process"
