"""Unit tests for GST continuous recorder day-folder rotation."""
from __future__ import annotations

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
