import json
from datetime import datetime
from pathlib import Path

import pytest

from evileye.api.core import playback_metadata_service as svc
from evileye.visualization_modules.overlay_config import (
    extract_zones_by_source,
    serialize_zones_for_overlay,
    video_size_for_source,
)


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
                "controller": {"use_database": False},
                "record": {"out_dir": str(root)},
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
    assert payload["zones"] == []
    assert payload["signalization"] is True
    assert payload["objects"][0]["event_active"] is True
    assert payload["debug_rois"] == []
    assert payload["coord_ref"] == {"w": 1920, "h": 1080}

    static_payload = svc.build_playback_static_metadata(
        camera="Cam1",
        run_id=1,
        source_id=0,
        frame_w=1920,
        frame_h=1080,
    )
    assert static_payload["zones"]
    assert static_payload["debug_rois"] == []
    assert static_payload["coord_ref"] == {"w": 1920, "h": 1080}


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
    params = {"controller": {"use_database": False}, "record": {"out_dir": str(root)}}
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    from evileye.api.core.playback_metadata_service import _load_dynamic_records

    objects, events = _load_dynamic_records(
        target=datetime.fromtimestamp(target_ts),
        camera="Cam1",
        date_folder=date,
        window_sec=1.0,
        params=params,
        source_id=0,
    )
    assert len(objects) == 1
    assert events == []


def test_load_dynamic_records_db_mode_skips_json(tmp_path, monkeypatch):
    params = {"controller": {"use_database": True}, "record": {"out_dir": str(tmp_path / "EvilEyeData")}}
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(tmp_path / "EvilEyeData"))
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
        params=params,
        source_id=0,
    )
    assert objects[0]["object_id"] == 9
    assert events == []


def test_build_playback_static_metadata_uses_live_serializer(tmp_path, monkeypatch):
    cfg = tmp_path / "config.json"
    cfg.write_text(
        json.dumps(
            {
                "events_detectors": {
                    "ZoneEventsDetector": {
                        "sources": {"0": [[[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]]},
                    }
                },
                "visualizer": {
                    "show_debug_info": True,
                    "show_zones": True,
                    "text_config": {"base_resolution": [1920, 1080]},
                },
                "pipeline": {
                    "sources": [{"source_ids": [0], "source_names": ["Cam1"]}],
                    "detectors": [{"source_ids": [0], "roi": [[[100, 50, 200, 150]]]}],
                },
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: json.loads(cfg.read_text(encoding="utf-8")))
    payload = svc.build_playback_static_metadata(
        camera="Cam1",
        run_id=1,
        source_id=0,
        frame_w=1920,
        frame_h=1080,
    )
    assert payload["zones"][0]["points"] == [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]
    assert payload["debug_rois"]
    assert payload["debug_rois"][0][0] == pytest.approx(100 / 1920, rel=1e-3)


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
    serialized = serialize_zones_for_overlay(zones[2], normalize=False)
    assert serialized[0]["points"] == [[0.5, 0.5], [0.6, 0.5], [0.6, 0.6]]


def test_extract_zones_web_editor_format():
    params = {
        "web_zones": {
            "0": [{"name": "ZoneA", "type": "polygon", "points": [[0.1, 0.1], [0.2, 0.1], [0.2, 0.2]]}],
        }
    }
    zones = extract_zones_by_source(params)
    assert 0 in zones
    assert zones[0][0][1][0] == [0.1, 0.1]


def test_normalize_zone_points_in_preview_render():
    from evileye.visualization_modules.preview_render import _normalize_zone_points

    norm = _normalize_zone_points([[960, 540], [1920, 1080]], 1920, 1080)
    assert norm[0][0] == pytest.approx(0.5, rel=1e-3)
    assert norm[1][1] == pytest.approx(1.0, rel=1e-3)
    unchanged = _normalize_zone_points([[0.2, 0.3], [0.4, 0.5]], 1920, 1080)
    assert unchanged == [[0.2, 0.3], [0.4, 0.5]]


def test_video_size_for_source_prefers_source_dimensions():
    params = {
        "visualization": {"text_config": {"base_resolution": [1920, 1080]}},
        "pipeline": {
            "sources": [
                {
                    "source_ids": [0],
                    "frame_width": 3840,
                    "frame_height": 2160,
                }
            ]
        },
    }
    assert video_size_for_source(params, 0) == (3840, 2160)


SPLIT_CONFIG = {
    "controller": {"use_database": False},
    "record": {"out_dir": "EvilEyeData"},
    "events_detectors": {
        "ZoneEventsDetector": {
            "sources": {
                "2": [
                    [
                        [0.08, 0.07],
                        [0.46, 0.62],
                        [0.35, 0.76],
                        [0.05, 0.10],
                    ]
                ],
            },
        },
    },
    "pipeline": {
        "sources": [
            {
                "split": True,
                "num_split": 2,
                "source_ids": [1, 2],
                "source_names": ["Cam2", "Cam3"],
                "src_coords": [
                    [0, 0, 2304, 1300],
                    [0, 1300, 2304, 1292],
                ],
            }
        ],
    },
}


def test_resolve_playback_coord_context_split_cam3():
    from evileye.visualization_modules.playback_coord import resolve_playback_coord_context

    ctx = resolve_playback_coord_context(
        SPLIT_CONFIG,
        camera="Cam3",
        source_id=2,
        frame_w=2304,
        frame_h=2592,
    )
    assert ctx.is_split is True
    assert ctx.logical_w == 2304
    assert ctx.logical_h == 1292
    assert ctx.src_coords == (0, 1300, 2304, 1292)


def test_static_metadata_split_zone_four_points(tmp_path, monkeypatch):
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: SPLIT_CONFIG)
    payload = svc.build_playback_static_metadata(
        camera="Cam3",
        run_id=1,
        source_id=2,
        frame_w=2304,
        frame_h=2592,
    )
    assert len(payload["zones"]) == 1
    assert len(payload["zones"][0]["points"]) == 4
    assert payload["coord_ref"] == {"w": 2304, "h": 1292}


def test_object_bbox_json_crop_pixels(tmp_path, monkeypatch):
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
                    "source_name": "Cam3",
                    "source_id": 2,
                    "object_id": 7,
                    "class_name": "person",
                    "bounding_box": {"x": 100, "y": 200, "width": 50, "height": 80},
                }
            ]
        ),
        encoding="utf-8",
    )
    cfg = dict(SPLIT_CONFIG)
    cfg["record"] = {"out_dir": str(root)}
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    payload = svc.build_playback_metadata(
        camera="Cam3",
        ts=target_ts,
        run_id=1,
        source_id=2,
        frame_w=2304,
        frame_h=2592,
    )
    assert len(payload["objects"]) == 1
    bbox = payload["objects"][0]["bbox"]
    assert bbox[1] == pytest.approx(200 / 1292, rel=1e-3)
    assert bbox[3] == pytest.approx(280 / 1292, rel=1e-3)


def test_dynamic_storage_mode_from_run_params(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-06-13"
    detections = root / "Detections" / date / "Metadata"
    detections.mkdir(parents=True)
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
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [0], "source_names": ["Cam1"]}]},
    }
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    monkeypatch.setattr(
        "evileye.api.core.journal_service.configured_storage_mode",
        lambda: "database",
    )

    payload = svc.build_playback_metadata(
        camera="Cam1",
        ts=datetime(2026, 6, 13, 10, 0, 0).timestamp(),
        run_id=1,
        source_id=0,
        frame_w=1920,
        frame_h=1080,
    )
    assert len(payload["objects"]) == 1


def test_source_match_by_source_id(tmp_path, monkeypatch):
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
                    "source_id": 2,
                    "object_id": 3,
                    "bounding_box": {"x": 10, "y": 20, "width": 30, "height": 40},
                }
            ]
        ),
        encoding="utf-8",
    )
    cfg = dict(SPLIT_CONFIG)
    cfg["record"] = {"out_dir": str(root)}
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    payload = svc.build_playback_metadata(
        camera="Cam3",
        ts=target_ts,
        run_id=1,
        source_id=2,
        frame_w=2304,
        frame_h=2592,
    )
    assert len(payload["objects"]) == 1
