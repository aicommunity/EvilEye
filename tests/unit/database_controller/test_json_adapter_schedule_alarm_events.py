"""ScheduleAlarmEvent has no frames of its own; the JSON adapter must still persist it."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from evileye.database_controller.json_adapter_schedule_alarm_events import JsonAdapterScheduleAlarmEvents
from evileye.events_detectors.event_schedule_alarm import ScheduleAlarmEvent


def _adapter(tmp_path: Path) -> JsonAdapterScheduleAlarmEvents:
    adapter = JsonAdapterScheduleAlarmEvents()
    adapter.set_params(image_dir=str(tmp_path))
    adapter.init()
    return adapter


def _event(finished: bool = False) -> ScheduleAlarmEvent:
    found = datetime(2026, 10, 19, 12, 0, 0)
    lost = datetime(2026, 10, 19, 12, 0, 9) if finished else None
    obj = SimpleNamespace(
        source_id=3, object_id=17, class_id=0, time_detected=found, time_lost=lost,
    )
    return ScheduleAlarmEvent(lost or found, "Alarm", obj, is_finished=finished)


def _records(tmp_path: Path) -> list[dict]:
    records = []
    for path in sorted((tmp_path / "Events").rglob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        records.extend(payload if isinstance(payload, list) else [payload])
    return records


def test_found_event_without_images_is_written(tmp_path):
    adapter = _adapter(tmp_path)

    adapter._insert_impl(_event())

    [record] = _records(tmp_path)
    assert record["source_id"] == 3 and record["object_id"] == 17 and record["class_id"] == 0
    assert record["preview_path"] == "" and record["frame_path"] == ""


def test_lost_event_without_images_is_written(tmp_path):
    adapter = _adapter(tmp_path)

    adapter._update_impl(_event(finished=True))

    [record] = _records(tmp_path)
    assert record["object_id"] == 17
    assert record["preview_path"] == "" and record["frame_path"] == ""
