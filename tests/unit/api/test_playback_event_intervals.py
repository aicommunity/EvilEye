import json
from datetime import datetime

import pytest

from evileye.api.core import playback_service as svc


@pytest.fixture
def events_data(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-19"
    meta = root / "Events" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "zone_events_entered.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-08-19T12:00:00",
                    "source_name": "Cam2",
                    "event_name": "ZoneA",
                    "zone_name": "ZoneA",
                    "zone_id": "zone-a",
                }
            ]
        ),
        encoding="utf-8",
    )
    (meta / "zone_events_left.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-08-19T12:00:04",
                    "source_name": "Cam2",
                    "event_name": "ZoneA",
                    "zone_name": "ZoneA",
                    "zone_id": "zone-a",
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    return root, date


def test_load_event_intervals_pairs_enter_and_left(events_data):
    _root, date = events_data
    intervals = svc.load_event_intervals(camera="Cam2", date=date)
    assert len(intervals) == 1
    interval = intervals[0]
    assert interval["camera"] == "Cam2"
    assert interval["zone_name"] == "ZoneA"
    assert interval["start_ts"] <= interval["end_ts"]
    start = datetime(2026, 8, 19, 12, 0, 0).timestamp()
    end = datetime(2026, 8, 19, 12, 0, 4).timestamp()
    assert abs(interval["start_ts"] - start) < 0.001
    assert abs(interval["end_ts"] - end) < 0.001


def test_load_event_intervals_filters_by_camera(events_data):
    _root, date = events_data
    assert svc.load_event_intervals(camera="OtherCam", date=date) == []
    assert len(svc.load_event_intervals(camera="Cam2", date=date)) == 1


@pytest.fixture
def events_data_source_id_only(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-28"
    meta = root / "Events" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "zone_events_entered.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 26455,
                    "ts": "2026-08-28T12:18:44.816889",
                    "source_id": 2,
                    "object_id": 661,
                    "zone_id": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    (meta / "zone_events_left.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 26455,
                    "ts": "2026-08-28T12:19:00.077717",
                    "source_id": 2,
                    "object_id": 661,
                    "zone_id": 0,
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_source_id_name_maps", lambda: ({2: "Cam3"}, {"Cam3": 2}))
    return root, date


def test_load_event_intervals_resolves_source_id_only(events_data_source_id_only):
    _root, date = events_data_source_id_only
    assert svc.load_event_intervals(camera="OtherCam", date=date) == []
    intervals = svc.load_event_intervals(camera="Cam3", date=date)
    assert len(intervals) == 1
    assert intervals[0]["camera"] == "Cam3"
    start = datetime.fromisoformat("2026-08-28T12:18:44.816889").timestamp()
    end = datetime.fromisoformat("2026-08-28T12:19:00.077717").timestamp()
    assert abs(intervals[0]["start_ts"] - start) < 0.001
    assert abs(intervals[0]["end_ts"] - end) < 0.001


def test_iter_event_rows_includes_source_id_without_name(events_data_source_id_only):
    _root, date = events_data_source_id_only
    rows = svc._iter_event_rows(cameras=["Cam3"], date=date)
    assert len(rows) == 2
    assert all(row.get("camera") == "Cam3" for row in rows)
