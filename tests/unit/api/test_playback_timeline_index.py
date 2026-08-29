"""Compact on-disk playback timeline index."""

from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from evileye.api.core import playback_timeline_index as idx
from evileye.api.core.singleflight import SingleFlight


def test_today_rebuild_sec_is_five_minutes():
    assert idx.TODAY_REBUILD_SEC == 300.0


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


def test_tick_row_to_item_accepts_preview_and_bbox():
    item = idx._tick_row_to_item([12.5, "found", 44, "preview.jpg", {"x": 1, "y": 2, "width": 3, "height": 4}])
    assert item["preview_path"] == "preview.jpg"
    assert item["bounding_box"]["width"] == 3


def test_compact_tick_row_roundtrip():
    row = idx._compact_tick_row(
        {
            "ts": 12.5,
            "kind": "found",
            "object_id": 44,
            "preview_path": "p.jpg",
            "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
        }
    )
    item = idx._tick_row_to_item(row)
    assert item["preview_path"] == "p.jpg"
    assert item["bounding_box"]["height"] == 4


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
    assert raw["version"] == idx.INDEX_VERSION
    by2 = idx.ensure_segment_index(date_folder=date, cameras=["Cam1"])
    assert by2["Cam1"][0]["end_ts"] == 200.0


def test_ensure_detection_ticks_serves_stale_without_rebuild(tmp_path, monkeypatch):
    date = "2026-08-17"
    meta_dir = tmp_path / "Detections" / date / "Metadata"
    meta_dir.mkdir(parents=True)
    (meta_dir / "objects_found.json").write_text("[]", encoding="utf-8")
    (meta_dir / "objects_lost.json").write_text("[]", encoding="utf-8")
    ticks_path = meta_dir / "detection_ticks.json"
    ticks_path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "date": date,
                "built_at": 1.0,
                "source_mtime": 0.0,
                "by_camera": {"Cam1": [[12.5, "found", 7]]},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "evileye.api.core.playback_metadata_service._load_params_for_run",
        lambda _run_id=None: {},
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_metadata_service._playback_data_dir",
        lambda _params: tmp_path,
    )

    rebuild_calls = {"n": 0}
    original = idx._rebuild_detection_ticks

    def _boom(**kwargs):
        rebuild_calls["n"] += 1
        return original(**kwargs)

    monkeypatch.setattr(idx, "_rebuild_detection_ticks", _boom)
    monkeypatch.setattr(idx, "schedule_detection_ticks_refresh", lambda *a, **k: None)

    out = idx.ensure_detection_ticks(date_folder=date, cameras=["Cam1"])
    assert out["Cam1"][0]["ts"] == 12.5
    assert out["Cam1"][0]["object_id"] == 7
    assert rebuild_calls["n"] == 0


def test_index_fresh_today_soft_ttl(tmp_path):
    date = "2099-01-01"  # not today → no soft TTL
    path = tmp_path / "idx.json"
    path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "built_at": time.time(),
                "source_mtime": 1.0,
            }
        ),
        encoding="utf-8",
    )
    assert idx._index_fresh(path, source_mtime=99.0, date_folder=date) is None

    today = time.strftime("%Y-%m-%d")
    path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "built_at": time.time() - 10.0,
                "source_mtime": 1.0,
            }
        ),
        encoding="utf-8",
    )
    assert idx._index_fresh(path, source_mtime=99.0, date_folder=today) is not None

    path.write_text(
        json.dumps(
            {
                "version": idx.INDEX_VERSION,
                "built_at": time.time() - (idx.TODAY_REBUILD_SEC + 5),
                "source_mtime": 1.0,
            }
        ),
        encoding="utf-8",
    )
    assert idx._index_fresh(path, source_mtime=99.0, date_folder=today) is None


def test_singleflight_shares_one_call():
    sf = SingleFlight()
    calls = {"n": 0}
    barrier = threading.Barrier(4)

    def work():
        barrier.wait()
        return sf.do(
            "k",
            lambda: (
                calls.__setitem__("n", calls["n"] + 1),
                time.sleep(0.05),
                "ok",
            )[-1],
        )

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: work(), range(4)))
    assert results == ["ok"] * 4
    assert calls["n"] == 1


def test_build_timeline_singleflight(monkeypatch):
    date = "2026-08-17"
    builds = {"n": 0}

    def fake_ensure_segment_index(**kwargs):
        return {"Cam1": [{"path": "a.mp4", "start_ts": 1.0, "end_ts": 2.0}]}

    def fake_ensure_detection_ticks(**kwargs):
        time.sleep(0.05)
        builds["n"] += 1
        return {"Cam1": [{"ts": 1.5, "kind": "found", "object_id": 1}]}

    def fake_ensure_event_intervals(**kwargs):
        return []

    monkeypatch.setattr(idx, "ensure_segment_index", fake_ensure_segment_index)
    monkeypatch.setattr(idx, "ensure_detection_ticks", fake_ensure_detection_ticks)
    monkeypatch.setattr(idx, "ensure_event_intervals", fake_ensure_event_intervals)

    barrier = threading.Barrier(3)

    def call():
        barrier.wait()
        return idx.build_timeline(date_folder=date, cameras=["Cam1"])

    with ThreadPoolExecutor(max_workers=3) as pool:
        outs = list(pool.map(lambda _: call(), range(3)))
    assert builds["n"] == 1
    assert all(o["by_camera"]["Cam1"]["detection_ticks"][0]["ts"] == 1.5 for o in outs)
