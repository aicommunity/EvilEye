"""Logical playback cameras from run config."""

import json
from pathlib import Path

from evileye.api.core.playback_service import list_logical_cameras, load_segments


def _write_config(tmp_path: Path) -> Path:
    cfg = {
        "pipeline": {
            "sources": [
                {
                    "split": False,
                    "source_ids": [0],
                    "source_names": ["Cam1"],
                },
                {
                    "split": True,
                    "num_split": 2,
                    "src_coords": [[0, 0, 100, 50], [0, 50, 100, 50]],
                    "source_ids": [1, 2],
                    "source_names": ["Cam2", "Cam3"],
                },
            ],
        },
    }
    path = tmp_path / "test-config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_list_logical_cameras_excludes_composite_id(tmp_path, monkeypatch):
    cfg_path = _write_config(tmp_path)
    streams = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "Cam2-Cam3"
    streams.mkdir(parents=True)
    (streams / "Cam2_20260613_120000.mp4").write_bytes(b"x")
    (streams / "Cam3_20260613_120100.mp4").write_bytes(b"x")
    (streams / "other.mp4").write_bytes(b"x")

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))

    monkeypatch.setattr(
        "evileye.api.core.playback_service._config_path_for_run",
        lambda run_id: str(cfg_path),
    )

    cameras = list_logical_cameras(run_id=1, date="2026-06-13")
    ids = [c["id"] for c in cameras]
    assert ids == ["Cam1", "Cam2", "Cam3"]
    assert "Cam2-Cam3" not in ids
    assert cameras[1]["split"] is True
    assert cameras[1]["src_coords"] == [0, 0, 100, 50]


def test_load_segments_split_prefix_filter(tmp_path, monkeypatch):
    base = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "Cam2-Cam3"
    base.mkdir(parents=True)
    cam2 = base / "Cam2_20260613_120000.mp4"
    cam3 = base / "Cam3_20260613_120100.mp4"
    other = base / "composite_only.mp4"
    cam2.write_bytes(b"x")
    cam3.write_bytes(b"x")
    other.write_bytes(b"x")

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))

    cam2_segments = load_segments("Cam2", date="2026-06-13")
    cam3_segments = load_segments("Cam3", date="2026-06-13")
    assert len(cam2_segments) == 1
    assert len(cam3_segments) == 1
    assert "Cam2_" in cam2_segments[0]["path"]
    assert "Cam3_" in cam3_segments[0]["path"]
