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
    segments = svc.load_segments("cam0")
    assert segments
    assert segments[0]["path"].endswith(".mp4")

    media = svc.resolve_media_path(str(seg))
    assert media.exists()


def test_path_traversal_rejected(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    root.mkdir()
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    try:
        svc.resolve_media_path("../etc/passwd")
        assert False, "expected PermissionError"
    except PermissionError:
        pass
