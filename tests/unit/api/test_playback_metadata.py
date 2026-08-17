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
                        "timestamp": "2026-06-13T10:00:00.100",
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
        "evileye.api.core.playback_metadata_service._db_available",
        lambda: True,
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


def test_json_active_track_between_found_and_lost(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T11:37:11.682288",
                        "source_name": "Cam2",
                        "source_id": 1,
                        "object_id": 808,
                        "class_name": "person",
                        "bounding_box": {"x": 1335, "y": 185, "width": 102, "height": 467},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (meta / "objects_lost.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 808,
                        "source_name": "Cam2",
                        "detected_timestamp": "2026-08-17T11:37:11.682288",
                        "lost_timestamp": "2026-08-17T11:37:13.316823",
                        "bounding_box": {"x": 1314, "y": 142, "width": 125, "height": 504},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {
            "sources": [
                {
                    "split": True,
                    "source_ids": [1, 2],
                    "source_names": ["Cam2", "Cam3"],
                    "src_coords": [[0, 0, 2304, 1300], [0, 1300, 2304, 1292]],
                }
            ]
        },
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    active = svc.build_playback_metadata(
        camera="Cam2",
        ts=datetime(2026, 8, 17, 11, 37, 11, 700000).timestamp(),
        run_id=1,
        source_id=1,
        frame_w=2304,
        frame_h=1300,
    )
    gone = svc.build_playback_metadata(
        camera="Cam2",
        ts=datetime(2026, 8, 17, 11, 37, 30).timestamp(),
        run_id=1,
        source_id=1,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(active["objects"]) == 1
    mid = svc.build_playback_metadata(
        camera="Cam2",
        ts=datetime(2026, 8, 17, 11, 37, 12, 500000).timestamp(),
        run_id=1,
        source_id=1,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(mid["objects"]) == 1
    mid_bbox = mid["objects"][0]["bbox"]
    found_x = 1335 / 2304
    lost_x = 1314 / 2304
    assert min(found_x, lost_x) < mid_bbox[0] < max(found_x, lost_x)
    assert len(gone["objects"]) == 0


def test_json_long_track_has_no_mid_lerp(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 464,
                        "source_name": "Cam4",
                        "timestamp": "2026-08-17T10:57:28",
                        "bounding_box": {"x": 100, "y": 100, "width": 50, "height": 80},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (meta / "objects_lost.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 464,
                        "source_name": "Cam4",
                        "lost_timestamp": "2026-08-17T10:59:37",
                        "bounding_box": {"x": 200, "y": 120, "width": 50, "height": 80},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {"controller": {"use_database": False}, "record": {"out_dir": str(root)}}
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    mid = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 59, 0).timestamp(),
        run_id=1,
    )
    found = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 57, 28).timestamp(),
        run_id=1,
    )
    lost = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 59, 37).timestamp(),
        run_id=1,
    )
    assert len(mid["objects"]) == 0
    assert len(found["objects"]) == 1
    assert len(lost["objects"]) == 1


def test_json_objects_cached_by_mtime(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    payload = {
        "objects": [
            {
                "object_id": 1,
                "source_name": "Cam1",
                "timestamp": "2026-08-17T11:00:00",
                "bounding_box": {"x": 10, "y": 10, "width": 20, "height": 20},
            }
        ]
    }
    (meta / "objects_found.json").write_text(json.dumps(payload), encoding="utf-8")
    (meta / "objects_lost.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    cfg = {"controller": {"use_database": False}, "record": {"out_dir": str(root)}}
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    loads = {"n": 0}
    orig = json.loads

    def counting_loads(raw, *args, **kwargs):
        loads["n"] += 1
        return orig(raw, *args, **kwargs)

    monkeypatch.setattr(svc.json, "loads", counting_loads)
    ts = datetime(2026, 8, 17, 11, 0, 0).timestamp()
    first = svc.build_playback_metadata(camera="Cam1", ts=ts, run_id=1)
    after_first = loads["n"]
    second = svc.build_playback_metadata(camera="Cam1", ts=ts, run_id=1)
    assert len(first["objects"]) == 1
    assert len(second["objects"]) == 1
    assert after_first >= 1
    assert loads["n"] == after_first


def test_db_events_without_objects_fall_back_to_json(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 9,
                        "source_name": "Cam1",
                        "timestamp": "2026-08-17T11:00:00",
                        "bounding_box": {"x": 10, "y": 10, "width": 20, "height": 20},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {"controller": {"use_database": True}, "record": {"out_dir": str(root)}}
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    monkeypatch.setattr(svc, "_playback_storage_mode", lambda _p: "database")
    monkeypatch.setattr(svc, "_db_available", lambda: True)
    monkeypatch.setattr(svc, "_load_objects_from_db", lambda *_a, **_k: [])
    monkeypatch.setattr(svc, "_load_events_from_db", lambda *_a, **_k: [{"event_type": "signal"}])

    payload = svc.build_playback_metadata(
        camera="Cam1",
        ts=datetime(2026, 8, 17, 11, 0, 0).timestamp(),
        run_id=1,
    )
    assert len(payload["objects"]) == 1


def test_json_found_without_lost_does_not_stick(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T10:57:08",
                        "source_name": "Cam4",
                        "source_id": 3,
                        "object_id": 456,
                        "class_name": "person",
                        "bounding_box": {"x": 10, "y": 20, "width": 30, "height": 40},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (meta / "objects_lost.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [3], "source_names": ["Cam4"]}]},
    }
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    near = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 57, 8).timestamp(),
        run_id=1,
        source_id=3,
        frame_w=2304,
        frame_h=1300,
    )
    later = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 59, 0).timestamp(),
        run_id=1,
        source_id=3,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(near["objects"]) == 1
    assert later["objects"] == []


def test_database_mode_falls_back_to_json_when_db_empty(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T10:59:00",
                        "source_name": "Cam4",
                        "object_id": 464,
                        "bounding_box": {"x": 10, "y": 20, "width": 30, "height": 40},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "controller": {"use_database": True},
        "database": {"image_dir": str(root)},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [3], "source_names": ["Cam4"]}]},
    }
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    monkeypatch.setattr(svc, "_db_available", lambda: True)
    monkeypatch.setattr(svc, "_load_objects_from_db", lambda *args, **kwargs: [])
    monkeypatch.setattr(svc, "_load_events_from_db", lambda *args, **kwargs: [])

    payload = svc.build_playback_metadata(
        camera="Cam4",
        ts=datetime(2026, 8, 17, 10, 59, 0).timestamp(),
        run_id=1,
        source_id=3,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(payload["objects"]) == 1
    assert payload["objects"][0]["object_id"] == 464


def test_load_detection_index_found_and_lost(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T11:37:11.682288",
                        "source_name": "Cam2",
                        "source_id": 1,
                        "object_id": 808,
                        "bounding_box": {"x": 1, "y": 2, "width": 3, "height": 4},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (meta / "objects_lost.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 808,
                        "source_name": "Cam2",
                        "lost_timestamp": "2026-08-17T11:37:13.316823",
                        "bounding_box": {"x": 5, "y": 6, "width": 7, "height": 8},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [1], "source_names": ["Cam2"]}]},
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)

    items = svc.load_detection_index(camera="Cam2", date_folder=date, run_id=1, source_id=1)
    assert len(items) == 2
    assert items[0]["kind"] == "found"
    assert items[1]["kind"] == "lost"
    assert items[0]["object_id"] == 808


def test_match_detections_at_exact(tmp_path, monkeypatch):
    found_ts = datetime(2026, 8, 17, 11, 37, 11, 682288).timestamp()
    items = [{"ts": found_ts, "kind": "found", "object_id": 1}]
    matched = svc.match_detections_at(items, found_ts)
    assert len(matched) == 1
    assert len(svc.match_detections_at(items, found_ts + 0.5)) == 0


def test_build_metadata_at_lost_ts(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    (meta / "objects_lost.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "object_id": 808,
                        "source_name": "Cam2",
                        "lost_timestamp": "2026-08-17T11:37:13.316823",
                        "bounding_box": {"x": 1314, "y": 142, "width": 125, "height": 504},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [1], "source_names": ["Cam2"]}]},
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    lost_ts = datetime(2026, 8, 17, 11, 37, 13, 316823).timestamp()
    payload = svc.build_playback_metadata(
        camera="Cam2",
        ts=lost_ts,
        run_id=1,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(payload["objects"]) == 1


def test_database_mode_falls_back_to_json_when_db_unavailable(tmp_path, monkeypatch):
    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T11:37:11.682288",
                        "source_name": "Cam2",
                        "object_id": 1,
                        "bounding_box": [100, 100, 200, 200],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    cfg = {
        "controller": {"use_database": True},
        "database": {"image_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [1], "source_names": ["Cam2"]}]},
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    monkeypatch.setattr(svc, "_db_available", lambda: False)

    payload = svc.build_playback_metadata(
        camera="Cam2",
        ts=datetime(2026, 8, 17, 11, 37, 11, 682288).timestamp(),
        run_id=1,
        frame_w=2304,
        frame_h=1300,
    )
    assert len(payload["objects"]) == 1


def test_split_cameras_do_not_share_sibling_detections(tmp_path, monkeypatch):
    from evileye.visualization_modules.playback_coord import source_aliases

    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    meta = root / "Detections" / date / "Metadata"
    meta.mkdir(parents=True)
    (meta / "objects_found.json").write_text(
        json.dumps(
            {
                "objects": [
                    {
                        "timestamp": "2026-08-17T11:18:15.092419",
                        "source_name": "Cam4",
                        "source_id": 3,
                        "object_id": 631,
                        "bounding_box": {"x": 999, "y": 106, "width": 57, "height": 87},
                    },
                    {
                        "timestamp": "2026-08-17T11:18:56.950308",
                        "source_name": "Cam5",
                        "source_id": 4,
                        "object_id": 634,
                        "bounding_box": {"x": 2147, "y": 440, "width": 154, "height": 372},
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (meta / "objects_lost.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {
            "sources": [
                {
                    "split": True,
                    "num_split": 2,
                    "source_ids": [3, 4],
                    "source_names": ["Cam4", "Cam5"],
                    "src_coords": [[0, 0, 2304, 1300], [0, 1300, 2304, 1292]],
                }
            ]
        },
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    svc.DETECTION_INDEX_CACHE.clear()

    assert source_aliases(cfg, "Cam4", 3) == {"Cam4", "Cam4-Cam5"}
    assert source_aliases(cfg, "Cam5", 4) == {"Cam5", "Cam4-Cam5"}

    cam4 = svc.load_detection_index(camera="Cam4", date_folder=date, run_id=1)
    cam5 = svc.load_detection_index(camera="Cam5", date_folder=date, run_id=1)
    assert [row["object_id"] for row in cam4] == [631]
    assert [row["object_id"] for row in cam5] == [634]

    ts = datetime(2026, 8, 17, 11, 18, 15, 92419).timestamp()
    payload = svc.build_playback_metadata(camera="Cam4", ts=ts, date=date, run_id=1)
    assert [obj["object_id"] for obj in payload["objects"]] == [631]


def test_detection_index_uses_media_pts_plus_sidecar(tmp_path, monkeypatch):
    from evileye.video_recorder.session_sidecar import sidecar_path_for_segment, write_session_sidecar

    root = tmp_path / "EvilEyeData"
    date = "2026-08-17"
    cam = root / "Streams" / date / "Cam4"
    cam.mkdir(parents=True)
    part0 = cam / "Cam4_20260817_014911_0_00000.mp4"
    part0.write_bytes(b"fake")
    filename_start = datetime(2026, 8, 17, 1, 49, 11).timestamp()
    mux_start = filename_start + 2.5
    write_session_sidecar(sidecar_path_for_segment(part0), mux_start, first_pts_ns=0)

    detections = root / "Detections" / date / "Metadata"
    detections.mkdir(parents=True)
    (detections / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "timestamp": "2026-08-17T01:49:11",
                    "media_pts_sec": 10.0,
                    "source_name": "Cam4",
                    "object_id": 7,
                    "bounding_box": [0, 0, 10, 10],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("EVILEYE_DATA_DIR", str(root))
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: {"pipeline": {"sources": []}})
    svc.DETECTION_INDEX_CACHE.clear()

    items = svc.load_detection_index(camera="Cam4", date_folder=date)
    assert items
    assert abs(items[0]["ts"] - (mux_start + 10.0)) < 0.05
