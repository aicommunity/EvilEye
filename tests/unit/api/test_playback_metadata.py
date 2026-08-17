import json
from datetime import datetime
from pathlib import Path

import pytest

from evileye.api.core import playback_metadata_service as svc
from evileye.visualization_modules.overlay_config import extract_zones_by_source, serialize_zones_for_overlay


def test_parse_event_timestamp_formats():
    assert svc.parse_event_timestamp("2026-06-13T10:00:00") == datetime(2026, 6, 13, 10, 0, 0)
    ts = datetime(2026, 6, 13, 10, 0, 0).timestamp()
    assert svc.parse_event_timestamp(ts) is not None


def test_build_playback_metadata_from_json(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    detections = root / "Detections" / date / "Metadata"
    events = root / "Events" / date / "Metadata"
    detections.mkdir(parents=True)
    events.mkdir(parents=True)

    target_ts = datetime(2026, 6, 13, 10, 0, 0).timestamp()
    (detections / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-06-13T10:00:00",
                    "source_name": "Cam1",
                    "object_id": 42,
                    "class_name": "person",
                    "confidence": 0.91,
                    "bounding_box": [192, 108, 384, 216],
                },
                {
                    "timestamp": "2026-06-13T10:05:00",
                    "source_name": "Cam1",
                    "object_id": 99,
                    "bounding_box": [0, 0, 10, 10],
                },
            ]
        ),
        encoding="utf-8",
    )
    (events / "zone_events_entered.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-06-13T10:00:00.500",
                    "source_name": "Cam1",
                    "object_id": 42,
                    "event_name": "ZoneA",
                    "bounding_box": [200, 120, 400, 240],
                }
            ]
        ),
        encoding="utf-8",
    )

    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "events_detectors": {
                    "ZoneEventsDetector": {
                        "sources": {
                            "0": [[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]],
                        }
                    }
                },
                "pipeline": {
                    "sources": [
                        {
                            "source_ids": [0],
                            "source_names": ["Cam1"],
                        }
                    ],
                    "detectors": [
                        {
                            "source_ids": [0],
                            "roi": [[[100, 50, 200, 150]]],
                        }
                    ],
                },
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: json.loads(cfg.read_text(encoding="utf-8")))
    monkeypatch.setattr(
        "evileye.api.core.journal_service.configured_storage_mode",
        lambda: "json",
    )

    payload = svc.build_playback_metadata(
        camera="Cam1",
        ts=target_ts,
        date=date,
        run_id=1,
        source_id=0,
    )

    assert payload["overlay"]["source_name"] == "Cam1"
    assert len(payload["objects"]) >= 1
    assert payload["objects"][0]["class_name"] == "person"
    assert payload["objects"][0]["bbox"][0] == pytest.approx(0.1, abs=0.01)
    assert payload["zones"]
    assert payload["signalization"] is True
    assert payload["objects"][0]["event_active"] is True
    assert payload["debug_rois"]


def test_build_playback_metadata_batch(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(
        svc,
        "build_playback_metadata",
        lambda **kwargs: {"overlay": {"source_name": kwargs["camera"]}, "objects": []},
    )
    result = svc.build_playback_metadata_batch(
        cameras=["Cam1", "Cam2"],
        ts=datetime(2026, 6, 13, 10, 0, 0).timestamp(),
        date="2026-06-13",
    )
    assert set(result.keys()) == {"Cam1", "Cam2"}


def test_load_dynamic_records_json_mode(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    detections = root / "Detections" / date / "Metadata"
    detections.mkdir(parents=True)
    target_ts = datetime(2026, 6, 13, 10, 0, 0).timestamp()
    (detections / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-06-13T10:00:00",
                    "source_name": "Cam1",
                    "object_id": 1,
                    "bounding_box": [0.1, 0.1, 0.2, 0.2],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(
        "evileye.api.core.journal_service.configured_storage_mode",
        lambda: "json",
    )
    from evileye.api.core.playback_metadata_service import _load_dynamic_records

    objects, events = _load_dynamic_records(
        target=datetime.fromtimestamp(target_ts),
        camera="Cam1",
        date_folder=date,
        window_sec=1.0,
    )
    assert len(objects) == 1
    assert events == []


def test_load_dynamic_records_db_mode_skips_json(tmp_path, monkeypatch):
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))
    monkeypatch.setattr(
        "evileye.api.core.journal_service.configured_storage_mode",
        lambda: "database",
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_metadata_service._load_objects_from_db",
        lambda *args, **kwargs: [{"object_id": 9, "bounding_box": [0, 0, 0.1, 0.1]}],
    )
    monkeypatch.setattr(
        "evileye.api.core.playback_metadata_service._load_events_from_db",
        lambda *args, **kwargs: [],
    )
    from evileye.api.core.playback_metadata_service import _load_dynamic_records

    objects, events = _load_dynamic_records(
        target=datetime(2026, 6, 13, 10, 0, 0),
        camera="Cam1",
        date_folder="2026-06-13",
        window_sec=1.0,
    )
    assert objects[0]["object_id"] == 9
    assert events == []


def test_build_playback_static_metadata(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "events_detectors": {
                    "ZoneEventsDetector": {
                        "sources": {"0": [[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]]},
                    }
                },
                "visualization": {"text_config": {"base_resolution": [1920, 1080]}},
                "pipeline": {"sources": [{"source_ids": [0], "source_names": ["Cam1"]}]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: json.loads(cfg.read_text(encoding="utf-8")))
    payload = svc.build_playback_static_metadata(camera="Cam1", run_id=1, source_id=0)
    assert payload["zones"]
    assert payload["overlay"]["source_name"] == "Cam1"
    assert payload["objects"] == []


def test_extract_zones_by_source():
    params = {
        "events_detectors": {
            "ZoneEventsDetector": {
                "sources": {"2": [[[0.5, 0.5], [0.6, 0.5], [0.6, 0.6]]]},
            }
        }
    }
    zones = extract_zones_by_source(params)
    assert 2 in zones
    serialized = serialize_zones_for_overlay(zones[2])
    assert serialized[0]["points"]
