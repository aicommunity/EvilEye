from pathlib import Path

from evileye.video_recorder.session_sidecar import (
    sidecar_path_for_segment,
    sidecar_path_from_splitmux_location,
    write_session_sidecar,
    read_session_sidecar_for_segment,
    pick_sidecar_start_ts,
)


def test_sidecar_path_strips_splitmux_index():
    video = Path("/data/Streams/2026-08-17/Cam4/Cam4_20260817_014911_0_00018.mp4")
    assert sidecar_path_for_segment(video).name == "Cam4_20260817_014911_0.session.json"


def test_sidecar_path_from_splitmux_location():
    location = "/data/Cam4_20260817_014911_0_%05d.mp4"
    assert sidecar_path_from_splitmux_location(location).name == "Cam4_20260817_014911_0.session.json"


def test_write_read_sidecar(tmp_path):
    video = tmp_path / "Cam4_20260817_014911_0_00000.mp4"
    video.write_bytes(b"fake")
    sidecar = sidecar_path_for_segment(video)
    write_session_sidecar(sidecar, 1000.5, first_pts_ns=123)
    data = read_session_sidecar_for_segment(video)
    assert data["start_ts"] == 1000.5
    assert data["first_pts_ns"] == 123
    assert pick_sidecar_start_ts(tmp_path) == 1000.5
