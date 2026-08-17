import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core import playback_metadata_service as svc


@pytest.fixture
def detections_client(tmp_path, monkeypatch):
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
    (meta / "objects_lost.json").write_text(json.dumps({"objects": []}), encoding="utf-8")
    cfg = {
        "controller": {"use_database": False},
        "record": {"out_dir": str(root)},
        "pipeline": {"sources": [{"source_ids": [1], "source_names": ["Cam2"]}]},
    }
    monkeypatch.setattr(svc, "_load_params_for_run", lambda _run_id: cfg)
    svc.DETECTION_INDEX_CACHE.clear()
    (tmp_path / "credentials.json").write_text(
        json.dumps(
            {
                "web_auth": {
                    "enabled": False,
                    "users": [{"username": "test", "password": "test", "role": "admin"}],
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    return TestClient(create_app())


def test_playback_detections_route(detections_client):
    res = detections_client.get(
        "/api/v1/playback/detections",
        params={"camera": "Cam2", "date": "2026-08-17", "run_id": 1},
    )
    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "found"
    assert items[0]["object_id"] == 808
    ts = datetime(2026, 8, 17, 11, 37, 11, 682288).timestamp()
    assert abs(items[0]["ts"] - ts) < 0.001
