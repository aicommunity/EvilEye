from evileye.database_controller.json_event_io import append_json_record, load_json_records
from evileye.database_controller.event_image_paths import event_image_dirs


def test_append_json_record(tmp_path):
    path = tmp_path / "meta" / "events.json"
    append_json_record(str(path), {"id": 1})
    append_json_record(str(path), {"id": 2})
    records = load_json_records(str(path))
    assert len(records) == 2
    assert records[1]["id"] == 2


def test_event_image_dirs_found_and_lost(tmp_path):
    day = str(tmp_path / "2026-01-01")
    found_prev, found_frame = event_image_dirs(day, is_lost=False)
    lost_prev, lost_frame = event_image_dirs(day, is_lost=True)
    assert "FoundPreviews" in found_prev
    assert "LostFrames" in lost_frame
