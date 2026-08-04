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
