"""The acceptance gate must score the counters run_once already computed."""

import json
from pathlib import Path

import scripts.tdps7_acceptance_gate as gate


def test_gate_scores_run_counters_when_log_path_is_absent(monkeypatch, tmp_path):
    clip = tmp_path / "clip.mp4"
    clip.write_bytes(b"clip")
    seen = {}

    def fake_make_clip(video, seconds, workdir):
        Path(workdir).mkdir(parents=True, exist_ok=True)
        return clip

    def fake_build_config(tree, made_clip, model, tracker):
        assert made_clip == clip
        assert tracker is True
        return {"model": model}

    def fake_run_once(tree, config, timeout):
        payload = json.loads(Path(config).read_text(encoding="utf-8"))
        seen["model"] = payload["model"]
        return {"detector_in": 100, "tracker_out": 95, "timed_out": False, "log": None}

    monkeypatch.setattr(gate, "make_clip", fake_make_clip)
    monkeypatch.setattr(gate, "build_config", fake_build_config)
    monkeypatch.setattr(gate, "run_once", fake_run_once)
    report = tmp_path / "report.md"

    code = gate.main([
        "--video", "clip.mp4",
        "--runs", "1",
        "--model", "models/yolov8n.pt",
        "--min-tracker-ratio", "0.92",
        "--report", str(report),
    ])

    assert code == 0
    assert seen["model"] == "models/yolov8n.pt"
    assert "0.950" in report.read_text(encoding="utf-8")
    assert "PASS" in report.read_text(encoding="utf-8")


def test_gate_fails_when_tracker_delivery_is_below_budget(monkeypatch, tmp_path):
    def fake_make_clip(video, seconds, workdir):
        Path(workdir).mkdir(parents=True, exist_ok=True)
        return tmp_path / "clip.mp4"

    monkeypatch.setattr(gate, "make_clip", fake_make_clip)
    monkeypatch.setattr(gate, "build_config", lambda *args, **kwargs: {"ok": True})
    monkeypatch.setattr(
        gate,
        "run_once",
        lambda *args, **kwargs: {"detector_in": 100, "tracker_out": 80, "timed_out": False},
    )

    code = gate.main(["--video", "clip.mp4", "--runs", "1", "--min-tracker-ratio", "0.92"])
    assert code == 1
