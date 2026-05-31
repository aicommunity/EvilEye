import json
from pathlib import Path

from evileye.pipelines.pipeline_surveillance import PipelineSurveillance


def test_pipeline_normalizes_ipc_mode_without_forcing_execution_mode():
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
    assert "execution_mode" not in normalized["sources"][0]
    assert normalized["sources"][0]["ipc_mode"] == "descriptor"
    assert normalized["detectors"][0]["execution_mode"] == "process"
    assert normalized["detectors"][0]["ipc_mode"] == "descriptor"
    assert "execution_mode" not in normalized["trackers"][0]


def test_pipeline_ipc_mode_defaults_to_standard():
    pipeline = PipelineSurveillance()
    src = {
        "pipeline_class": "PipelineSurveillance",
        "sources": [{"source_ids": [0]}],
    }
    normalized = pipeline._normalize_pipeline_params(src)
    assert normalized["ipc_mode"] == "standard"
    assert normalized["sources"][0]["ipc_mode"] == "standard"


def test_real_configs_execution_mode_policy():
    repo_root = Path(__file__).resolve().parents[3]
    single_sp = json.loads(
        (repo_root / "configs" / "single_video_singleprocess.json").read_text()
    )
    poly = json.loads((repo_root / "configs" / "poly-videos-gst.json").read_text())

    assert single_sp["pipeline"]["sources"][0]["execution_mode"] == "thread"
    assert single_sp["pipeline"]["detectors"][0]["execution_mode"] == "thread"

    assert "execution_mode" not in poly["pipeline"]["sources"][0]
    assert "execution_mode" not in poly["pipeline"]["detectors"][0]
    assert "execution_mode" not in poly["pipeline"]["trackers"][0]


def test_deploy_samples_pin_thread_execution_mode():
    repo_root = Path(__file__).resolve().parents[3]
    sample = json.loads(
        (repo_root / "evileye" / "samples_configs" / "single_video.json").read_text()
    )
    for key in ("sources", "detectors", "trackers"):
        assert sample["pipeline"][key][0]["execution_mode"] == "thread"
