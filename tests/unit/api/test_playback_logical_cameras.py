"""Logical playback cameras from run config."""

import json
from pathlib import Path

from evileye.api.core.playback_service import list_logical_cameras, load_segments


def _write_config(tmp_path: Path, sources: list[dict]) -> Path:
    cfg = {"pipeline": {"sources": sources}}
    path = tmp_path / "test-config.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    return path


def test_list_logical_cameras_excludes_composite_id(tmp_path, monkeypatch):
    cfg_path = _write_config(
        tmp_path,
        [
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
    )
    streams = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "Cam2-Cam3"
    streams.mkdir(parents=True)
    # Recorder writes only source_names[0] prefix into the composite folder.
    (streams / "Cam2_20260613_120000.mp4").write_bytes(b"x")
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
    assert cameras[1]["segment_count"] == 1
    assert cameras[2]["segment_count"] == 1
    assert cameras[2]["available"] is True


def test_load_segments_split_parts_share_primary_prefix(tmp_path, monkeypatch):
    """Any logical part of a composite folder sees the shared recording set."""
    base = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "Alpha-Beta"
    base.mkdir(parents=True)
    primary = base / "Alpha_20260613_120000.mp4"
    junk = base / "composite_only.mp4"
    primary.write_bytes(b"x")
    junk.write_bytes(b"x")

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))

    alpha = load_segments("Alpha", date="2026-06-13")
    beta = load_segments("Beta", date="2026-06-13")
    assert len(alpha) == 1
    assert len(beta) == 1
    assert alpha[0]["path"] == beta[0]["path"]
    assert "Alpha_" in alpha[0]["path"]


def test_load_segments_three_way_split_shares_primary(tmp_path, monkeypatch):
    base = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "A-B-C"
    base.mkdir(parents=True)
    (base / "A_20260613_120000_0_00000.mp4").write_bytes(b"x")

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))

    for name in ("A", "B", "C"):
        segs = load_segments(name, date="2026-06-13")
        assert len(segs) == 1
        assert segs[0]["path"].endswith("A_20260613_120000_0_00000.mp4")


def test_list_logical_cameras_split_counts_shared_segments(tmp_path, monkeypatch):
    cfg_path = _write_config(
        tmp_path,
        [
            {
                "split": True,
                "num_split": 2,
                "src_coords": [[0, 0, 100, 50], [0, 50, 100, 50]],
                "source_ids": [1, 2],
                "source_names": ["Alpha", "Beta"],
            },
        ],
    )
    streams = tmp_path / "EvilEyeData" / "Streams" / "2026-06-13" / "Alpha-Beta"
    streams.mkdir(parents=True)
    (streams / "Alpha_20260613_120000.mp4").write_bytes(b"x")

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))
    monkeypatch.setattr(
        "evileye.api.core.playback_service._config_path_for_run",
        lambda run_id: str(cfg_path),
    )

    cameras = list_logical_cameras(run_id=1, date="2026-06-13")
    by_id = {c["id"]: c for c in cameras}
    assert by_id["Alpha"]["segment_count"] == 1
    assert by_id["Beta"]["segment_count"] == 1
    assert by_id["Beta"]["available"] is True
