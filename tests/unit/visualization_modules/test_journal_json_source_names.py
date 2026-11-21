"""Events written with only a numeric source id must still carry the camera name."""
from __future__ import annotations

from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource

PARAMS = {"pipeline": {"sources": [
    {"camera": "rtsp://10.0.0.1", "source_ids": [0, 1], "source_names": ["Cam1", "Cam2"]},
]}}


def _source(tmp_path):
    return JsonLabelJournalDataSource(str(tmp_path), PARAMS)


def test_schedule_alarm_rows_get_the_camera_name(tmp_path):
    source = _source(tmp_path)
    for event_type in ("schedule_alarm_found", "schedule_alarm_lost"):
        row = source._map_item(
            {"event_id": 5, "ts": "2026-10-19T12:00:00", "source_id": 1, "object_id": 9, "class_id": 0},
            event_type, "2026-10-19", 0,
        )
        assert row["source_name"] == "Cam2" and row["source_id"] == 1


def test_attribute_rows_get_the_camera_name(tmp_path):
    source = _source(tmp_path)
    row = source._map_item(
        {"event_id": 6, "ts": "2026-10-19T12:00:00", "source_id": 0, "object_id": 3, "class_id": 0},
        "attr_found", "2026-10-19", 0,
    )
    assert row["source_name"] == "Cam1"


def test_a_recorded_source_name_wins_and_unknown_ids_stay_unnamed(tmp_path):
    source = _source(tmp_path)
    recorded = source._map_item(
        {"event_id": 7, "ts": "2026-10-19T12:00:00", "source_id": 0, "source_name": "Renamed"},
        "schedule_alarm_found", "2026-10-19", 0,
    )
    unknown = source._map_item(
        {"event_id": 8, "ts": "2026-10-19T12:00:00", "source_id": 99},
        "schedule_alarm_found", "2026-10-19", 0,
    )
    assert recorded["source_name"] == "Renamed"
    assert unknown["source_name"] is None
