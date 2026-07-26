from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from evileye.api.app import create_app
from evileye.api.core import journal_service


@pytest.fixture()
def journal_client(tmp_path, monkeypatch):
    base = tmp_path / "EvilEyeData"
    preview_dir = base / "Detections" / "2026-06-13" / "Images" / "FoundPreviews"
    preview_dir.mkdir(parents=True)
    preview = preview_dir / "obj_preview.jpg"
    preview.write_bytes(b"\xff\xd8\xff" + b"x" * 100)

    video_rel = "Events/2026-06-13/Videos/Cam1/clip.mp4"
    video = base / video_rel
    video.parent.mkdir(parents=True)
    video.write_bytes(b"x" * 2000)

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
    app = create_app()
    return TestClient(app), str(preview.name), video_rel


def test_filters_meta_returns_dates(journal_client):
    client, _preview, _video = journal_client
    response = client.get("/api/v1/journals/filters/meta")
    assert response.status_code == 200
    payload = response.json()
    assert "dates" in payload
    assert "source_names" in payload


def test_events_grouped_enriched_row(journal_client):
    client, _preview, _video = journal_client
    metadata = Path("EvilEyeData/Detections/2026-06-13/Metadata")
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 1,
                    "timestamp": "2026-06-13T10:00:00",
                    "source_id": 0,
                    "source_name": "Cam1",
                    "object_id": 42,
                    "class_name": "person",
                    "image_filename": "obj_preview.jpg",
                    "date_folder": "2026-06-13",
                }
            ]
        ),
        encoding="utf-8",
    )
    response = client.get("/api/v1/journals/objects/grouped?page=0&size=5")
    assert response.status_code == 200
    payload = response.json()
    assert payload["available"] is True
    assert payload["items"]
    row = payload["items"][0]
    assert "row_key" in row
    assert row.get("date_folder") == "2026-06-13"


def test_preview_serves_jpeg(journal_client):
    client, preview_name, _video = journal_client
    response = client.get(
        f"/api/v1/journals/preview?path={preview_name}&date=2026-06-13&journal_type=objects"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("image/")


def test_preview_mode_lost_prefers_lost_previews(journal_client, tmp_path):
    client, preview_name, _video = journal_client
    base = tmp_path / "EvilEyeData"
    lost_dir = base / "Detections" / "2026-06-13" / "Images" / "LostPreviews"
    lost_dir.mkdir(parents=True, exist_ok=True)
    lost_name = "obj_lost.jpg"
    lost_file = lost_dir / lost_name
    lost_file.write_bytes(b"\xff\xd8\xff" + b"l" * 100)

    response = client.get(
        f"/api/v1/journals/preview?path={lost_name}&date=2026-06-13&journal_type=objects&mode=lost"
    )
    assert response.status_code == 200
    assert response.content.startswith(b"\xff\xd8\xffl")


def test_video_serves_mp4_with_range(journal_client):
    client, _preview, video_rel = journal_client
    response = client.get(f"/api/v1/journals/video?path={video_rel}")
    assert response.status_code == 200
    assert response.headers.get("accept-ranges") == "bytes"
    assert "video/mp4" in response.headers.get("content-type", "")


def test_path_traversal_blocked(journal_client):
    client, _preview, _video = journal_client
    response = client.get("/api/v1/journals/video?path=../../../etc/passwd")
    assert response.status_code in {403, 404}


def test_row_meta_after_grouped_load(journal_client):
    client, _preview, _video = journal_client
    metadata = Path("EvilEyeData/Detections/2026-06-13/Metadata")
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "event_id": 1,
                    "timestamp": "2026-06-13T10:00:00",
                    "source_id": 0,
                    "source_name": "Cam1",
                    "object_id": 42,
                    "class_name": "person",
                    "image_filename": "obj_preview.jpg",
                    "date_folder": "2026-06-13",
                    "bounding_box": [0.1, 0.1, 0.2, 0.2],
                }
            ]
        ),
        encoding="utf-8",
    )
    grouped = client.get("/api/v1/journals/objects/grouped?page=0&size=5")
    assert grouped.status_code == 200
    row = grouped.json()["items"][0]
    row_key_value = row["row_key"]
    meta = client.get(f"/api/v1/journals/row-meta?row_key={row_key_value}&journal_type=objects")
    assert meta.status_code == 200
    payload = meta.json()
    assert payload.get("bbox_found") == [0.1, 0.1, 0.2, 0.2]


def test_journal_stats_endpoint(journal_client):
    client, _preview, _video = journal_client
    metadata = Path("EvilEyeData/Detections/2026-06-13/Metadata")
    metadata.mkdir(parents=True, exist_ok=True)
    (metadata / "objects_found.json").write_text(
        json.dumps(
            [
                {
                    "object_id": 1,
                    "timestamp": "2026-06-13T10:00:00",
                    "source_id": 0,
                    "source_name": "Cam1",
                    "class_name": "person",
                    "image_filename": "obj_preview.jpg",
                    "bounding_box": {"x": 0, "y": 0, "width": 1, "height": 1},
                }
            ]
        ),
        encoding="utf-8",
    )
    response = client.get("/api/v1/journals/stats?date=2026-06-13")
    assert response.status_code == 200
    payload = response.json()
    assert payload.get("available") is True
    assert payload.get("objects_total", 0) >= 1


def test_preview_cache_control_header(journal_client):
    client, preview_name, _video = journal_client
    response = client.get(
        f"/api/v1/journals/preview?path={preview_name}&date=2026-06-13&journal_type=objects"
    )
    assert response.status_code == 200
    assert response.headers.get("cache-control") == "public, max-age=3600"


def test_video_mkv_content_type(journal_client, tmp_path):
    client, _preview, _video = journal_client
    base = tmp_path / "EvilEyeData"
    mkv_rel = "Events/2026-06-13/Videos/Cam1/clip.mkv"
    mkv = base / mkv_rel
    mkv.parent.mkdir(parents=True, exist_ok=True)
    mkv.write_bytes(b"x" * 2000)
    response = client.get(f"/api/v1/journals/video?path={mkv_rel}")
    assert response.status_code == 200
    assert "matroska" in response.headers.get("content-type", "") or "video" in response.headers.get("content-type", "")
