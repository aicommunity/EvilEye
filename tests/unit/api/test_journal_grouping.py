from __future__ import annotations

from evileye.api.core.journal_grouping import group_events_rows, group_objects_rows


def test_zone_grouping_key_matches_qt():
    rows = group_events_rows(
        [
            {"event_type": "zone_entered", "source_id": 1, "object_id": 42, "ts": "2026-01-01", "source_name": "Cam1"},
            {"event_type": "zone_left", "source_id": 1, "object_id": 42, "ts": "2026-01-02", "source_name": "Cam1"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["event"] == "ZoneEvent"
    assert rows[0]["time_lost"] == "2026-01-02"
    assert rows[0].get("found_event") is not None
    assert rows[0].get("date_folder") is not None or rows[0].get("found_event")


def test_attr_grouping_by_object_id_only():
    rows = group_events_rows(
        [
            {"event_type": "attr_found", "object_id": 7, "source_id": 0, "ts": "t1", "event_name": "x"},
            {"event_type": "attr_lost", "object_id": 7, "source_id": 1, "ts": "t2", "event_name": "x"},
        ]
    )
    assert len(rows) == 1
    assert rows[0]["event"] == "AttributeEvent"


def test_objects_grouping_includes_date_folder():
    rows = group_objects_rows(
        [
            {
                "event_type": "found",
                "object_id": 1,
                "ts": "2026-06-13T10:00:00",
                "source_name": "Cam1",
                "date_folder": "2026-06-13",
                "image_filename": "a.jpg",
            }
        ]
    )
    assert rows[0]["date_folder"] == "2026-06-13"
    assert rows[0]["preview"] == "a.jpg"


def test_group_objects_rows_sorted_newest_first():
    rows = group_objects_rows(
        [
            {
                "event_type": "found",
                "object_id": 1,
                "ts": "2026-06-13T09:00:00",
                "source_name": "Cam1",
                "date_folder": "2026-06-13",
            },
            {
                "event_type": "found",
                "object_id": 2,
                "ts": "2026-06-13T11:00:00",
                "source_name": "Cam1",
                "date_folder": "2026-06-13",
            },
        ]
    )
    assert len(rows) == 2
    assert rows[0]["time"] >= rows[1]["time"]
