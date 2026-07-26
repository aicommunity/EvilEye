from __future__ import annotations

import json
from unittest.mock import patch

from evileye.visualization_modules.journal_data_source_json import JsonLabelJournalDataSource


def test_second_fetch_reuses_cache_without_reparsing(tmp_path):
    base = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    metadata_dir = base / "Detections" / date / "Metadata"
    metadata_dir.mkdir(parents=True)
    found_file = metadata_dir / "objects_found.json"
    found_file.write_text(
        json.dumps(
            [
                {
                    "object_id": 1,
                    "timestamp": "2026-06-13T10:00:00",
                    "image_filename": "Detections/2026-06-13/Images/FoundPreviews/a_preview.jpeg",
                    "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
                    "confidence": 0.9,
                    "class_id": 0,
                    "class_name": "person",
                    "source_id": 1,
                    "source_name": "cam1",
                }
            ]
        ),
        encoding="utf-8",
    )

    source = JsonLabelJournalDataSource(str(base))
    source.set_date(date)
    read_calls: list[str] = []
    original_read = source._read_file

    def tracked_read(filepath, event_type, date_folder):
        read_calls.append(filepath)
        return original_read(filepath, event_type, date_folder)

    with patch.object(source, "_read_file", side_effect=tracked_read):
        source.begin_request()
        first = source.fetch(0, 10, {"journal_kind": "objects"}, sort=[("ts", "desc")])
        second_total = source.get_total({"journal_kind": "objects"})

    assert len(first) == 1
    assert second_total == 1
    assert len(read_calls) == 1

    source.begin_request()
    third = source.fetch(0, 10, {"journal_kind": "objects"}, sort=[("ts", "desc")])
    assert len(third) == 1
    assert len(read_calls) == 1
