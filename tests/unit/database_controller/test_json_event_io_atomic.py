import json
import os

from evileye.database_controller.json_event_io import append_json_record, load_json_records


def test_append_json_record_atomic(tmp_path):
    file_path = str(tmp_path / "nested" / "events.json")
    append_json_record(file_path, {"id": 1})
    append_json_record(file_path, {"id": 2})
    records = load_json_records(file_path)
    assert records == [{"id": 1}, {"id": 2}]
    assert not os.path.exists(f"{file_path}.tmp")
