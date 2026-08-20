"""Compact on-disk playback timeline index."""

from __future__ import annotations

import json
from pathlib import Path

from evileye.api.core import playback_timeline_index as idx


def test_filter_segments_window():
    rows = [
        {"path": "a", "start_ts": 10.0, "end_ts": 20.0},
        {"path": "b", "start_ts": 30.0, "end_ts": 40.0},
    ]
    assert len(idx.filter_segments_window(rows, 15, 35)) == 2
    assert len(idx.filter_segments_window(rows, 21, 29)) == 0
    assert len(idx.filter_segments_window(rows, None, 15)) == 1


def test_tick_row_to_item_accepts_compact_triples():
    item = idx._tick_row_to_item([12.5, "found", 44])
    assert item["ts"] == 12.5
    assert item["kind"] == "found"
    assert item["object_id"] == 44


def test_segment_index_roundtrip(tmp_path, monkeypatch):
    date = "2026-08-17"
    streams = tmp_path / "Streams" / date / "Cam1"
    streams.mkdir(parents=True)
    # empty day — index should still write
    monkeypatch.setattr(
        "evileye.api.core.playback_service.data_dir",
        lambda: tmp_path,
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_service.discover_cameras",
        lambda _date=None: [{"id": "Cam1"}],
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_service.load_segments_uncached",
        lambda camera, from_ts=None, to_ts=None, date=None: [
            {
                "path": str(streams / "Cam1_x.mp4"),
                "start_ts": 100.0,
                "end_ts": 200.0,
                "duration_ms": 100000,
                "camera": camera,
                "playable": True,
            }
        ],
    )
    by1 = idx.ensure_segment_index(date_folder=date, cameras=["Cam1"])
    assert by1["Cam1"][0]["start_ts"] == 100.0
    path = idx.segment_index_path(tmp_path / "Streams" / date)
    assert path.is_file()
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw["version"] == 1
    by2 = idx.ensure_segment_index(date_folder=date, cameras=["Cam1"])
    assert by2["Cam1"][0]["end_ts"] == 200.0
