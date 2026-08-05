import json
import os
from pathlib import Path

from evileye.api.core import playback_service as svc


def test_discover_cameras_and_segments(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-04" / "cam0"
    cam.mkdir(parents=True)
    seg = cam / "20260804_120000.mp4"
    seg.write_bytes(b"fake")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))

    cameras = svc.discover_cameras("2026-08-04")
    assert any(c["id"] == "cam0" for c in cameras)
    segments = svc.load_segments("cam0", date="2026-08-04")
    assert segments
    assert segments[0]["path"].endswith(".mp4")

    media = svc.resolve_media_path(str(seg))
    assert media.exists()


def test_data_dir_falls_back_to_database_image_dir(tmp_path, monkeypatch):
    """When EVILEYE_DATA_DIR is unset, use database.image_dir from current run config."""
    root = tmp_path / "media_data"
    cam = root / "Streams" / "2026-08-05" / "Cam1"
    cam.mkdir(parents=True)
    (cam / "Cam1_20260805_010000_0_00000.mp4").write_bytes(b"fake")
    cfg = tmp_path / "poly.json"
    cfg.write_text(
        '{"database": {"image_dir": %s}, "pipeline": {"sources": []}}' % json.dumps(str(root)),
        encoding="utf-8",
    )
    monkeypatch.delenv("EVILEYE_DATA_DIR", raising=False)
    monkeypatch.setattr(
        svc,
        "_load_current_run_config",
        lambda: (str(cfg), {"database": {"image_dir": str(root)}}),
    )
    svc._data_dir_cache = None

    assert svc.data_dir() == root.resolve()
    cameras = svc.discover_cameras("2026-08-05")
    assert any(c["id"] == "Cam1" for c in cameras)


def test_composite_folder_resolution(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-04" / "Cam2-Cam3"
    cam.mkdir(parents=True)
    (cam / "Cam2_20260804_091017_0_00000.mp4").write_bytes(b"fake")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))

    cameras = svc.discover_cameras("2026-08-04")
    ids = {c["id"] for c in cameras}
    assert "Cam2" in ids or "Cam2-Cam3" in ids
    segs = svc.load_segments("Cam2", date="2026-08-04")
    assert segs


def test_path_traversal_rejected(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    root.mkdir()
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    try:
        svc.resolve_media_path("../etc/passwd")
        assert False, "expected PermissionError"
    except PermissionError:
        pass


def test_date_dirs_covering_range(tmp_path):
    base = tmp_path / "Streams"
    (base / "2026-08-04").mkdir(parents=True)
    (base / "2026-08-05").mkdir(parents=True)
    (base / "2026-08-06").mkdir(parents=True)
    start = __import__("datetime").datetime(2026, 8, 4, 12, 0, 0).timestamp()
    end = __import__("datetime").datetime(2026, 8, 5, 18, 0, 0).timestamp()
    dirs = svc._date_dirs_covering(base, from_ts=start, to_ts=end)
    names = {p.name for p in dirs}
    assert "2026-08-04" in names
    assert "2026-08-05" in names
    assert "2026-08-06" not in names


def test_load_segments_multi_day_from_to(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    for day, hh in [("2026-08-04", "120000"), ("2026-08-05", "130000")]:
        cam = root / "Streams" / day / "cam0"
        cam.mkdir(parents=True)
        (cam / f"{day.replace('-', '')}_{hh}.mp4").write_bytes(b"fake")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_video_duration_sec", lambda _p: 60.0)

    start = __import__("datetime").datetime(2026, 8, 4, 0, 0, 0).timestamp()
    end = __import__("datetime").datetime(2026, 8, 5, 23, 59, 59).timestamp()
    segments = svc.load_segments("cam0", from_ts=start, to_ts=end, date=None)
    assert len(segments) >= 2
    days = {__import__("datetime").datetime.fromtimestamp(s["start_ts"]).strftime("%Y-%m-%d") for s in segments}
    assert "2026-08-04" in days
    assert "2026-08-05" in days
