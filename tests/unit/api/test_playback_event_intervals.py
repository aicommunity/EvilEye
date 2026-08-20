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
