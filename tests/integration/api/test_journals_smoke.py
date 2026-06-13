"""Integration smoke tests for web journal API endpoints."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core import journal_service


@pytest.fixture()
def smoke_client(tmp_path, monkeypatch):
    base = tmp_path / "EvilEyeData"
    date = "2026-06-13"

    found_dir = base / "Detections" / date / "Images" / "FoundPreviews"
    lost_dir = base / "Detections" / date / "Images" / "LostPreviews"
    found_dir.mkdir(parents=True)
    lost_dir.mkdir(parents=True)
    found_preview = found_dir / "obj_found.jpg"
    lost_preview = lost_dir / "obj_lost.jpg"
    found_preview.write_bytes(b"\xff\xd8\xff" + b"f" * 100)
    lost_preview.write_bytes(b"\xff\xd8\xff" + b"l" * 100)

    video_rel = f"Events/{date}/Videos/Cam1/clip.mp4"
    video = base / video_rel
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x" * 4096)

    metadata = base / "Detections" / date / "Metadata"
    metadata.mkdir(parents=True)
    (metadata / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 1,
                    "timestamp": f"{date}T10:00:00",
                    "source_id": 0,
                    "source_name": "Cam1",
                    "object_id": 42,
                    "class_name": "person",
                    "image_filename": "obj_found.jpg",
                    "date_folder": date,
                }
            ]
        ),
        encoding="utf-8",
    )

    config_path = tmp_path / "poly.json"
    config_path.write_text(
        json.dumps(
            {
                "controller": {"use_database": False, "image_dir": str(base)},
                "pipeline": {"sources": [{"source_names": ["Cam1"], "source_ids": [0]}]},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        journal_service,
        "get_current_run_summary",
        lambda: {"config_path": str(config_path)},
    )
    return TestClient(create_app()), date, found_preview.name, lost_preview.name, video_rel


def test_journals_smoke_flow(smoke_client):
    client, date, found_name, lost_name, video_rel = smoke_client

    meta = client.get("/api/v1/journals/filters/meta")
    assert meta.status_code == 200
    meta_payload = meta.json()
    assert date in meta_payload.get("dates", [])

    objects = client.get(f"/api/v1/journals/objects/grouped?page=0&size=10&date={date}")
    assert objects.status_code == 200
    objects_payload = objects.json()
    assert objects_payload.get("available") is True
    assert objects_payload.get("items")

    events = client.get(f"/api/v1/journals/events/grouped?page=0&size=5&date={date}")
    assert events.status_code == 200

    found = client.get(
        f"/api/v1/journals/preview?path={found_name}&date={date}&journal_type=objects&mode=found"
    )
    assert found.status_code == 200
    assert found.content.startswith(b"\xff\xd8\xff")

    lost = client.get(
        f"/api/v1/journals/preview?path={lost_name}&date={date}&journal_type=objects&mode=lost"
    )
    assert lost.status_code == 200
    assert lost.content.startswith(b"\xff\xd8\xff")

    frame = client.get(
        f"/api/v1/journals/frame?path={found_name}&date={date}&journal_type=objects&mode=found"
    )
    assert frame.status_code == 200

    video = client.get(f"/api/v1/journals/video?path={video_rel}")
    assert video.status_code == 200
    assert video.headers.get("accept-ranges") == "bytes"

    row_key_value = objects_payload["items"][0]["row_key"]
    meta = client.get(f"/api/v1/journals/row-meta?row_key={row_key_value}&journal_type=objects")
    assert meta.status_code == 200
    assert "bbox_found" in meta.json() or meta.json().get("bbox_found") is None
