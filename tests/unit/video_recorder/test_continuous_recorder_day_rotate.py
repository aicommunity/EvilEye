"""Unit tests for GST continuous recorder day-folder rotation."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from evileye.video_recorder.continuous_recorder_gst import GstContinuousRecorder
from evileye.video_recorder.recording_params import RecordingParams
from evileye.video_recorder.recorder_base import SourceMeta


def test_fragment_location_rotates_day_folder(tmp_path):
    rec = GstContinuousRecorder()
    params = RecordingParams(
        enabled=True,
        continuous_recording_enabled=True,
        out_dir=str(tmp_path),
        container="mp4",
        filename_tmpl="{source_name}_{start_time}_{seq}.{ext}",
    )
    rec.start(
        SourceMeta(source_name="Cam1", source_address=None, source_type=None, source_names=["Cam1"]),
        params,
    )
    rec._camera_folder = "Cam1"
    rec._source_name = "Cam1"
    rec._streams_base = Path(tmp_path) / "Streams"

    day1 = datetime(2026, 9, 8, 23, 50, 0)
    path0 = rec.fragment_location_for_id(0, now=day1)
    path1 = rec.fragment_location_for_id(1, now=day1)
    assert "2026-09-08" in path0
    assert path0.endswith("_00000.mp4")
    assert path1.endswith("_00001.mp4")
    assert Path(path0).parent == Path(path1).parent

    day2 = datetime(2026, 9, 9, 0, 5, 0)
    path2 = rec.fragment_location_for_id(2, now=day2)
    assert "2026-09-09" in path2
    assert path2.endswith("_00002.mp4")
    assert Path(path2).parent != Path(path0).parent
    # New day opens a new session stem (index continues from fragment_id).
    assert Path(path2).name.startswith("Cam1_20260909_")
    sidecar = Path(str(rec._session_stem) + ".session.json")
    assert sidecar.is_file()
    rec.stop()


def test_day_rotate_sidecar_keeps_original_session_start(tmp_path):
    """Midnight folder rotate must not rewrite start_ts while fragment_id continues."""
    rec = GstContinuousRecorder()
    params = RecordingParams(
        enabled=True,
        continuous_recording_enabled=True,
        out_dir=str(tmp_path),
        container="mp4",
        filename_tmpl="{source_name}_{start_time}_{seq}.{ext}",
    )
    rec.start(
        SourceMeta(source_name="Cam1", source_address=None, source_type=None, source_names=["Cam1"]),
        params,
    )
    rec._camera_folder = "Cam1"
    rec._source_name = "Cam1"
    rec._streams_base = Path(tmp_path) / "Streams"

    day1 = datetime(2026, 9, 8, 23, 50, 0)
    rec.fragment_location_for_id(0, now=day1)
    anchor = day1.timestamp()
    rec._session_start_ts = anchor

    day2 = datetime(2026, 9, 9, 0, 5, 0)
    path2 = rec.fragment_location_for_id(77, now=day2)
    assert "2026-09-09" in path2
    assert path2.endswith("_00077.mp4")

    sidecar = Path(str(rec._session_stem) + ".session.json")
    assert sidecar.is_file()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert abs(float(data["start_ts"]) - anchor) < 0.01
    # Must not be wall-clock of the new calendar day.
    assert abs(float(data["start_ts"]) - day2.timestamp()) > 60.0
    rec.stop()
