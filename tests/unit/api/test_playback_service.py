import json
import os
import struct
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
    # Non-primary logical part must share the same recording files.
    segs_cam3 = svc.load_segments("Cam3", date="2026-08-04")
    assert segs_cam3
    assert segs_cam3[0]["path"] == segs[0]["path"]


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
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 60.0)

    start = __import__("datetime").datetime(2026, 8, 4, 0, 0, 0).timestamp()
    end = __import__("datetime").datetime(2026, 8, 5, 23, 59, 59).timestamp()
    segments = svc.load_segments("cam0", from_ts=start, to_ts=end, date=None)
    assert len(segments) >= 2
    days = {__import__("datetime").datetime.fromtimestamp(s["start_ts"]).strftime("%Y-%m-%d") for s in segments}
    assert "2026-08-04" in days
    assert "2026-08-05" in days


def test_load_segments_uses_neighbor_gap_not_opencv(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-05" / "Cam1"
    cam.mkdir(parents=True)
    (cam / "Cam1_20260805_010000_0_00000.mp4").write_bytes(b"fake")
    (cam / "Cam1_20260805_013000_0_00001.mp4").write_bytes(b"fake")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 1800.0)

    segs = svc.load_segments("Cam1", date="2026-08-05")
    assert len(segs) == 2
    # First segment ends when the next starts (30 minutes), no OpenCV needed.
    assert abs(segs[0]["duration_ms"] - 30 * 60 * 1000) < 1000
    assert segs[0]["end_ts"] == segs[1]["start_ts"]


def test_load_segments_splitmux_same_session_timestamp(tmp_path, monkeypatch):
    """GStreamer splitmux keeps one session datetime; index selects the slot."""
    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-08" / "Cam1"
    cam.mkdir(parents=True)
    for idx in range(3):
        (cam / f"Cam1_20260808_010020_0_{idx:05d}.mp4").write_bytes(b"fake")
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 1800.0)

    segs = svc.load_segments("Cam1", date="2026-08-08")
    assert len(segs) == 3
    assert abs(segs[1]["start_ts"] - segs[0]["start_ts"] - 1800) < 1
    assert abs(segs[2]["start_ts"] - segs[1]["start_ts"] - 1800) < 1
    assert segs[0]["end_ts"] == segs[1]["start_ts"]
    assert segs[1]["end_ts"] == segs[2]["start_ts"]
    # Three contiguous 30-min slots (~1.5h coverage from session start).
    assert abs(segs[2]["start_ts"] - segs[0]["start_ts"] - 3600) < 1


def test_load_segments_splitmux_uses_mtime_when_media_drifts(tmp_path, monkeypatch):
    """Real splitmux parts are a few seconds short of segment_length_sec."""
    from datetime import datetime

    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-17" / "Cam4-Cam5"
    cam.mkdir(parents=True)
    session = datetime(2026, 8, 17, 1, 49, 11).timestamp()
    part_len = 1795.0
    files = []
    for idx in range(20):
        path = cam / f"Cam4_20260817_014911_0_{idx:05d}.mp4"
        path.write_bytes(b"fake")
        close = session + (idx + 1) * part_len
        os.utime(path, (close, close))
        files.append(path)
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 1800.0)

    segs = {Path(s["path"]).name: s for s in svc.load_segments("Cam4", date="2026-08-17")}
    part18 = segs["Cam4_20260817_014911_0_00018.mp4"]
    part19 = segs["Cam4_20260817_014911_0_00019.mp4"]
    tick_1059 = datetime(2026, 8, 17, 10, 59, 27).timestamp()
    tick_1118 = datetime(2026, 8, 17, 11, 18, 15).timestamp()
    assert part18["start_ts"] <= tick_1059 <= part18["end_ts"]
    assert part19["start_ts"] <= tick_1118 <= part19["end_ts"]
    assert tick_1118 - part19["start_ts"] < 60
    # index*1800 would start part 18 ~66s later and keep 11:18:15 in the previous file.
    assert part18["start_ts"] < session + 18 * 1800 - 30


def _minimal_mp4(duration_sec: float, timescale: int = 1000) -> bytes:
    duration = int(round(duration_sec * timescale))
    mvhd_payload = struct.pack(">BBBBIIII", 0, 0, 0, 0, 0, 0, timescale, duration)
    mvhd = struct.pack(">I4s", 8 + len(mvhd_payload), b"mvhd") + mvhd_payload
    moov = struct.pack(">I4s", 8 + len(mvhd), b"moov") + mvhd
    ftyp_payload = b"isom" + struct.pack(">I", 0) + b"isom"
    ftyp = struct.pack(">I4s", 8 + len(ftyp_payload), b"ftyp") + ftyp_payload
    return ftyp + moov


def test_mp4_duration_reads_mvhd(tmp_path):
    path = tmp_path / "clip.mp4"
    path.write_bytes(_minimal_mp4(1796.353))
    assert abs(svc._mp4_duration_sec(str(path)) - 1796.353) < 0.002


def test_load_segments_splitmux_ignores_first_file_finalize_delay(tmp_path, monkeypatch):
    """async-finalize mtime of part 0 is ~12s after media; must not shift later parts."""
    from datetime import datetime

    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-17" / "Cam4-Cam5"
    cam.mkdir(parents=True)
    session = datetime(2026, 8, 17, 1, 49, 11).timestamp()
    media = [1796.353] + [1795.2] * 19
    wall = session
    for idx, dur in enumerate(media):
        path = cam / f"Cam4_20260817_014911_0_{idx:05d}.mp4"
        path.write_bytes(_minimal_mp4(dur))
        wall += dur
        extra = 11.7 if idx == 0 else 0.0
        os.utime(path, (wall + extra, wall + extra))
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 1800.0)
    svc._MP4_DURATION_CACHE.clear()

    segs = {Path(s["path"]).name: s for s in svc.load_segments("Cam4", date="2026-08-17")}
    part0 = segs["Cam4_20260817_014911_0_00000.mp4"]
    part1 = segs["Cam4_20260817_014911_0_00001.mp4"]
    part18 = segs["Cam4_20260817_014911_0_00018.mp4"]
    part19 = segs["Cam4_20260817_014911_0_00019.mp4"]
    assert abs(part0["start_ts"] - session) < 0.1
    assert abs(part1["start_ts"] - (session + 1796.353)) < 0.1
    # mtime chain would have started part 1 ~12s later.
    assert part1["start_ts"] < session + 1808
    tick_1059 = datetime(2026, 8, 17, 10, 59, 27).timestamp()
    tick_1118 = datetime(2026, 8, 17, 11, 18, 15).timestamp()
    assert part18["start_ts"] <= tick_1059 <= part18["end_ts"]
    assert part19["start_ts"] <= tick_1118 <= part19["end_ts"]
    assert tick_1118 - part19["start_ts"] < 60


def test_load_segments_prefers_sidecar_session_start(tmp_path, monkeypatch):
    """First muxed-frame wall clock beats the pipeline-setup filename."""
    from datetime import datetime

    from evileye.video_recorder.session_sidecar import sidecar_path_for_segment, write_session_sidecar

    root = tmp_path / "EvilEyeData"
    cam = root / "Streams" / "2026-08-17" / "Cam4"
    cam.mkdir(parents=True)
    filename_start = datetime(2026, 8, 17, 1, 49, 11).timestamp()
    mux_start = filename_start + 2.5
    part0 = cam / "Cam4_20260817_014911_0_00000.mp4"
    part0.write_bytes(_minimal_mp4(1796.353))
    write_session_sidecar(sidecar_path_for_segment(part0), mux_start, first_pts_ns=0)
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_configured_segment_length_sec", lambda: 1800.0)
    svc._MP4_DURATION_CACHE.clear()

    segs = svc.load_segments("Cam4", date="2026-08-17")
    assert abs(segs[0]["start_ts"] - mux_start) < 0.05
    assert segs[0]["start_ts"] - filename_start > 2.0
